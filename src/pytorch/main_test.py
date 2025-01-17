import torch
from torch.utils import data
import torchvision.transforms as transforms
import torch.optim as optim
import os,pickle
import numpy as np
from PIL import Image
import scipy.misc
import time
# from skimage.transform import rescale

from SS_CNN import *
from Standard_CNN import *
from Antialiased_SSCNN import *
from SI_ConvNet import *


# This is the testbench for the
# MNIST-Scale, FMNIST-Scale and CIFAR-10-Scale datasets.
# The networks and network architecture are defiend
# within their respective libraries

os.environ["CUDA_VISIBLE_DEVICES"] = "1"

from torch.multiprocessing import set_start_method
set_start_method('spawn', force=True)


class Dataset(data.Dataset):
	'Characterizes a dataset for PyTorch'
	def __init__(self, dataset_name, inputs, labels,transform=None):
		'Initialization'
		self.labels = labels
		# self.list_IDs = list_IDs
		self.inputs = inputs
		self.transform = transform
		self.dataset_name = dataset_name


	def __len__(self):
		'Denotes the total number of samples'
		return self.inputs.shape[0]

	def cutout(self,img,x,y,size):
		size = int(size/2)
		lx = np.maximum(0,x-size)
		rx = np.minimum(img.shape[0],x+size)
		ly = np.maximum(0, y - size)
		ry = np.minimum(img.shape[1], y + size)

		img[lx:rx,ly:ry,:] = 0
		return img

	def __getitem__(self, index):
		'Generates one sample of data'
		# Select sample
		# ID = self.list_IDs[index]
		# Load data and get label
		# X = torch.load('data/' + ID + '.pt')
		img = self.inputs[index]
		if self.dataset_name == 'STL10':
			img = np.transpose(img, [1, 2, 0])

		# Cutout module begins
		# xcm = int(np.random.rand()*95)
		# ycm = int(np.random.rand()*95)
		# img = self.cutout(img,xcm,ycm,24)
		#Cutout module ends

		# print(np.max(img),np.min(img))

		# img = np.float32(scipy.misc.imresize(img,2.0)) # Cannot use due to the update of SciPy
		# img = np.float32(rescale(img, 2.0))
		width, height = img.shape[:2]
		img = np.float32(Image.fromarray(img).resize([2*width, 2*height]))
		# h, w = img.shape[:2]
		# img = transform.resize(img, (h*2, w*2))

		# Optional:
		# img = img / np.max(img)


		if self.transform is not None:
			img = self.transform(img)

		y = int(self.labels[index])

		return img, y



def load_dataset(dataset_name,split,training_size,augmentation=None):
	os.chdir(dataset_name)
	file_names = os.listdir()

	listdict = []
	for i in range(len(file_names)):
		if file_names[i][-8] == str(split):
			print("Load dataset split: ", file_names[i])
			tmp = pickle.load(open(file_names[i], 'rb'))
			break
	listdict.append(tmp)

	listdict[-1]['train_data'] = np.float32(listdict[-1]['train_data'][0:training_size, :, :])
	listdict[-1]['train_label'] = listdict[-1]['train_label'][0:training_size]
	# listdict[-1]['val_data'] = np.float32(listdict[-1]['val_data'])
	# listdict[-1]['val_label'] = listdict[-1]['val_label']
	listdict[-1]['test_data'] = np.float32(listdict[-1]['test_data'])
	listdict[-1]['test_label'] = listdict[-1]['test_label']

	os.chdir('..')

	if augmentation is not None:
		os.chdir(augmentation)
		file_names = os.listdir()
		for i in range(len(file_names)):
			if file_names[i][-8] == str(split):
				print("Load dataset split: ", file_names[i])
				tmp = pickle.load(open(file_names[i], 'rb'))
				break

		listdict[-1]['train_data'] = np.float32(np.append(listdict[-1]['train_data'], tmp['train_data'][0:training_size, :, :], axis=0))
		listdict[-1]['train_label'] = np.append(listdict[-1]['train_label'], tmp['train_label'][0:training_size], axis=0)

		os.chdir('..')

	return listdict


def train_network(net,trainloader,init_rate, step_size,gamma,total_epochs,weight_decay):
	# params = add_weight_decay(net, l2_normal,l2_special,name_special)
	optimizer = optim.SGD(net.parameters(),lr=init_rate, momentum=0.9,weight_decay=weight_decay)
	scheduler = StepLR(optimizer, step_size=step_size, gamma=gamma)
	criterion = nn.CrossEntropyLoss()
	net = net.cuda()

	start_time = time.time()
	net = net.train()

	for epoch in range(total_epochs):
		torch.cuda.empty_cache()
		scheduler.step()
		running_loss = 0.0

		for i, data in enumerate(trainloader, 0):
			# get the inputs
			inputs, labels = data
			inputs = inputs.cuda()
			labels = labels.cuda()
			# zero the parameter gradients
			optimizer.zero_grad()
			outputs = net(inputs)
			loss = criterion(outputs, labels)
			loss.backward()
			optimizer.step()
			del inputs, labels # delete intermediate

	print("Training completed.")
	total_time = time.time()-start_time
	print("Total training time: %.3f" % total_time)

	net = net.eval()
	return net


def test_network(net,testloader,test_labels):
	net = net.eval()
	correct = torch.tensor(0)
	total = len(test_labels)
	dataiter = iter(testloader)

	with torch.no_grad():
		for i in range(int(len(test_labels) / testloader.batch_size)):
			images, labels = dataiter.next()
			images = images.cuda()
			labels = labels.cuda()
			outputs = net(images)
			_, predicted = torch.max(outputs, 1)
			correct = correct + torch.sum(predicted == labels)
			torch.cuda.empty_cache()

	accuracy = float(correct)/float(total)
	return accuracy



def run_test(training_size):
	# dataset_name = '/data2/team16b/MNIST-Scale-New'
	# augmentation = '/data2/team16b/MNIST-Scale-For-Augmentation'
	dataset_name = '/data2/team16b/FMNIST-Scale-New'
	# augmentation = '/data2/team16b/FMNIST-Scale-For-Augmentation'

	# val_splits = [2,3,4,5]
	val_splits = [0,1,2,3,4,5]

	# Good result on MNIST-Scale 1000 Training
	# training_size = 1000
	# batch_size = 100
	# init_rate = 0.05
	# weight_decay = 0.06

	test_size = 10000
	batch_size = 400
	init_rate = 0.04
	decay_normal = 0.04
	decay_special = 0.04

	step_size = 10

	gamma = 0.7
	total_epochs = 50


	Networks_to_train = [Net_steerinvariant_mnist_scale()]
	# Networks_to_train = [standard_CNN_mnist_scale(), Net_scaleinvariant_mnist_scale(), Net_steerinvariant_mnist_scale()]
	network_name = ['SS-CNN']
	# network_name = ['Standard-CNN', 'SI-ConvNet', 'SS-CNN']

	transform_train = transforms.Compose(
		[transforms.ToTensor(),
		 ])
	transform_test = transforms.Compose(
		[transforms.ToTensor(),
		 ])

	# listdict = load_dataset(dataset_name, val_splits, training_size, test_size)
	accuracy_all = np.zeros((len(val_splits),len(Networks_to_train)))

	for i in range(len(val_splits)):
		listdict = load_dataset(dataset_name, val_splits[i], training_size)
		# listdict = load_dataset(dataset_name, val_splits[i], training_size, augmentation)

		train_data = listdict[-1]['train_data']
		train_labels = listdict[-1]['train_label']
		test_data = listdict[-1]['test_data']
		test_labels = listdict[-1]['test_label']

		Data_train = Dataset(dataset_name,train_data,train_labels,transform_train)
		Data_test = Dataset(dataset_name, test_data, test_labels, transform_test)
		trainloader = torch.utils.data.DataLoader(Data_train, batch_size=batch_size, shuffle=False, num_workers=4)
		testloader = torch.utils.data.DataLoader(Data_test, batch_size=int(len(test_labels)/200),shuffle=False, num_workers=2)

		for j in range(len(Networks_to_train)):
			print("Training network:", network_name[j], "\t training_size =", training_size, "\t test_size =", test_size)
			# print("Training network:", network_name[j], "\t training_size =", training_size*2, "\t test_size =", test_size)
			net = train_network(Networks_to_train[j],trainloader, init_rate, step_size,gamma,total_epochs,decay_normal)
			accuracy = test_network(net,testloader,test_labels)
			accuracy_train = test_network(net,trainloader,train_labels)

			print(network_name[j])
			print("Train:",accuracy_train,"Test:",accuracy,"\n")
			accuracy_all[i,j] = accuracy

			# save_path = '../../experiment/'+str(int(training_size/1000))+'k/'+network_name[j]+'/'+network_name[j]+str(i)+'.pt'
			
			# if not os.path.exists(save_path):
			# 	try:
			# 	    original_umask = os.umask(0)
			# 	    os.makedirs(save_path, desired_permission)
			# 	finally:
			# 	    os.umask(original_umask)
			# torch.save(net.state_dict(), save_path)

			del net, accuracy, accuracy_train

		# for j in range(len(Networks_to_train)):
		# 	print("Result on split", val_splits[i])
		# 	print(network_name[j])
		# 	print(accuracy_all[i,j])


	# print("Mean Accuracies of Networks:", np.mean(accuracy_all,0))
	# print("Standard Deviations of Networks:",np.std(accuracy_all,0))
	# for j in range(len(Networks_to_train)):
	# 	print(network_name[j])
	# 	print(accuracy_all[:,j])



if __name__ == "__main__":
	torch.set_default_tensor_type('torch.cuda.FloatTensor')
	training_size = [10000, 8000, 6000, 4000, 2000]
	for i in range(len(training_size)):
		run_test(training_size[i])


