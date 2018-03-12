import argparse

import numpy as np
import tensorflow as tf
import pandas
from sklearn import preprocessing
from sklearn import metrics
from tensorflow.python.framework import ops
from sklearn.model_selection import train_test_split
from collections import Counter
from scipy.sparse import csc_matrix
from sklearn.model_selection import KFold

print ("Start getting data...")
# Date input
parser = argparse.ArgumentParser('Trains SVM model over protein vectors')
parser.add_argument('--sample', type=str, default='../trained_models/protein_pfam_vector.csv')
args = parser.parse_args()

# Read csv
print("Read_csv...")
dataframe = pandas.read_csv(args.sample, header=None)
dataset = dataframe.values
family = dataset[:,1]
vectors = dataset[:,2:].astype(float)
data_size = len(family)
print("Done...\n")

# Label encoder
print("Labeling...")
label_encoder = preprocessing.LabelEncoder()
label_encoder.fit(family)
families_encoded = np.array(label_encoder.transform(family), dtype=np.int32)
family = None
depth = families_encoded.max() + 1
print("Done...\n")

# Find family that have a protein more than 400
famous_list = []
family_count = {}
for family in families_encoded:
    if family in family_count:
        family_count[family] += 1
    else:
        family_count[family] = 1
        
    if family_count[family] >= 400 and family not in famous_list:
        famous_list.append(family)

# Make One_hot encoding and sparse matrics
print("One hot Encoding...")
rows = np.arange(families_encoded.size)
cols = families_encoded
data = np.ones(families_encoded.size)
y_vals = csc_matrix((data, (rows, cols)), shape=(families_encoded.size, depth))
rows, cols, data = None, None, None
print("Done...\n")

# Normalize vectors for accuracy
min_on_training = vectors.min(axis=0)
range_on_training = (vectors - min_on_training).max(axis=0)
x_vals = (vectors - min_on_training) / range_on_training
print ("Done...\n")

# Initialize training variables
batch_size = 100
learning_rate = 0.01

# tf.Graph
with tf.Graph().as_default() as graph:
    # Initialize placeholders for training
    x_data = tf.placeholder(shape=[None, 100], dtype=tf.float32)
    y_target = tf.placeholder(shape=[depth, None], dtype=tf.float32)
    prediction_grid = tf.placeholder(shape=[None, 100], dtype=tf.float32)

    # Create variables for svm
    b = tf.Variable(tf.random_normal(shape=[depth, batch_size]), name="b")

    # Gaussian (RBF) kernel
    gamma = tf.constant(-4.0)
    dist = tf.reduce_sum(tf.square(x_data), 1)
    dist = tf.reshape(dist, [-1,1])
    sq_dists = tf.multiply(2., tf.matmul(x_data, tf.transpose(x_data)))
    my_kernel = tf.exp(tf.multiply(gamma, tf.abs(sq_dists)))
    
    # Declare function to do reshape/batch multiplication
    def reshape_matmul(mat):
        v1 = tf.expand_dims(mat, 1)
        v2 = tf.reshape(v1, [depth, batch_size, 1])
        return(tf.matmul(v2, v1))
    
    # Compute SVM Model
    first_term = tf.reduce_sum(b)
    b_vec_cross = tf.matmul(tf.transpose(b), b)
    y_target_cross = reshape_matmul(y_target)
    
    second_term = tf.reduce_sum(tf.multiply(my_kernel, tf.multiply(b_vec_cross, y_target_cross)),[1,2])
    loss = tf.reduce_sum(tf.negative(tf.subtract(first_term, second_term)))
    
    # Gaussian (RBF) prediction kernel
    rA = tf.reshape(tf.reduce_sum(tf.square(x_data), 1),[-1,1])
    rB = tf.reshape(tf.reduce_sum(tf.square(prediction_grid), 1),[-1,1])
    pred_sq_dist = tf.add(tf.subtract(rA, tf.multiply(2., tf.matmul(x_data, tf.transpose(prediction_grid)))), tf.transpose(rB))
    pred_kernel = tf.exp(tf.multiply(gamma, tf.abs(pred_sq_dist)))
    
    prediction_output = tf.matmul(tf.multiply(y_target,b), pred_kernel)
    prediction = tf.argmax(prediction_output-tf.expand_dims(tf.reduce_mean(prediction_output,1), 1), 0)
    
    accuracy = tf.reduce_mean(tf.cast(tf.equal(prediction, tf.argmax(y_target,0)), tf.float32))
    
    # Initialize placeholders for accuracy
    labels = tf.placeholder(shape=[None], dtype=tf.float32)
    prediction_i = tf.placeholder(shape=[None], dtype=tf.float32)
    
    # Define the metric and update operations
    actual = tf.argmax(y_target, 0)
    accuracy_with_confusion, tf_metric_update = tf.metrics.accuracy(labels, 
                                                                    prediction_i, 
                                                                    name="my_metric")

    # Isolate the variables stored behind the scenes by the metric operation
    running_vars = tf.get_collection(tf.GraphKeys.LOCAL_VARIABLES, scope="my_metric")

    # Define initializer to initialize/reset running variables
    running_vars_initializer = tf.variables_initializer(var_list=running_vars)

    # Declare optimizer
    my_opt = tf.train.GradientDescentOptimizer(learning_rate)
    train_step = my_opt.minimize(loss)


    # Initialize variables
    init = tf.global_variables_initializer()

sess = tf.Session(graph=graph)

sess.run(init)
sess.run(running_vars_initializer)

# loss and accuracy array declaration
loss_vec = []
test_batch_accuracy = []

# Collection of trained data and actual data
used_test_y = np.zeros(shape=(0))
predicted = np.zeros(shape=(0))

#Initialize KFOLD Object
seed = 7
kfold = KFold(n_splits=10, shuffle=True, random_state=seed)

#K fold cross validation
for train_index, test_index in kfold.split(x_vals, y_vals.toarray()):
    train_set, test_set = x_vals[train_index], x_vals[test_index]
    sparse_encoded_train_label, sparse_encoded_test_label = y_vals[train_index], y_vals[test_index]
    i = 0

    # Training
    while (i + 1) * batch_size < len(train_set):
        index = [j for j in range(batch_size * i, batch_size * (i + 1) )]
        rand_x = train_set[index]
        np_y = sparse_encoded_train_label[index].toarray()
        rand_y = np_y.transpose()
        
        # Training models
        sess.run(train_step, feed_dict={x_data: rand_x, y_target: rand_y})
        
        # Calulate loss
        temp_loss = sess.run(loss, feed_dict={x_data: rand_x, y_target: rand_y})
        loss_vec.append(temp_loss)

        i += 1
        if (i+1)%25==0:
            print('train_Step #' + str(i+1))
            print('Loss = ' + str(temp_loss))
            
    # Test
    i = 0
    while (i + 1) * batch_size < len(test_set):
        index = [j for j in range(batch_size * i, batch_size * (i + 1) )]
        rand_x = test_set[index]
        np_y = sparse_encoded_test_label[index].toarray()
        rand_y = np_y.transpose()
        
        # Get predicted data and encodered actual data of onehot actual data
        prediction_one_dim = sess.run(prediction, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
        actuals = sess.run(actual, feed_dict={y_target: rand_y})
        
        # Calulate accuracy for normal mathod
        acc_temp = sess.run(accuracy, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
        
        # Calulate accuracy for confusion matrix
        sess.run(tf_metric_update, feed_dict={labels: actuals, prediction_i: prediction_one_dim})
        accuracy_with_confusion_val = sess.run(accuracy_with_confusion, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
             
        # Store actual data and predicted data
        used_test_y = np.append(used_test_y, actuals)
        predicted = np.append(predicted, prediction_one_dim)
        
        test_batch_accuracy.append(acc_temp)
        
        if (i+1)%25==0:
            print('\ntest_Step #' + str(i+1))
            print('test_accuracy = ' + str(acc_temp))
            print('confusion_accuracy = ' + str(accuracy_with_confusion_val))
            
        i += 1

    print('Batch accuracy: ' + str(acc_temp))
    print('\n')
    print('\n')

# Calulate total accuracy of full data
accuracy_with_confusion_val = sess.run(accuracy_with_confusion, feed_dict={labels: used_test_y, 
                                                                            prediction_i: predicted})
print('Total accuracy: ' + str(float(sum(test_batch_accuracy)) / float(len(test_batch_accuracy))))
print('Total accuracy: ' + str(accuracy_with_confusion_val))

# Writing File
with open('rbf_result.txt', 'w') as outfile:
    for famous_family_num in famous_list:
        family_name = label_encoder.inverse_transform(famous_family_num)
        # Initialize array for confusion metrix
        predicted_fam = []
        actual_fam = []
        
        # Calulate confusion metrix
        tp = 0
        fp = 0
        tn = 0
        fn = 0
        for index, actual_family_num in enumerate(used_test_y):
            if famous_family_num == actual_family_num:
                actual_fam.append(actual_family_num)
                predicted_fam.append(predicted[index])
                if actual_family_num == predicted[index]:
                    tp += 1 #TP
                else:
                    fn += 1 #FP
            else:
                if famous_family_num == predicted[index]:
                    fp += 1
                else:
                    tn += 1
                    
        # Calulate accuracy, sensitivity, specificity
        fam_accuracy = float(tp + tn) / float(tp+fp+tn+fn)
        sensitivity = float(tp) / float(tp + fn)
        specificity = float(tn) /float(tn + fp)
        
        # Write at file
        outfile.write('{}\t{}\t{}\t\t{:.5f}\t{:.5f}\t{:.5f}\n'.format(family_name, tp, len(actual_fam), 
                      specificity, sensitivity, fam_accuracy))
    

# =============================================================================
# # Test with famous families 
# prediction_total = []
# for famous_family_num in famous_list:
#     print('=======family_name = {}======'.format(label_encoder.inverse_transform(famous_family_num)))
#     indices = []
#     counter = 0
#     for family_num in families_encoded:
#         if famous_family_num == family_num:
#             indices.append(counter)
#         counter += 1
# 
#     i = 0
#     batch_accuracy = []
# 
#     while (i + 1) * batch_size < len(indices):
#         index = indices[i * batch_size : (i+1) * batch_size]
#         rand_x = x_vals[index]
#         np_y = y_vals[index].toarray()
#         rand_y = np_y.transpose()
#         test_acc_temp = sess.run(accuracy, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         #prediction1_output_val = sess.run(prediction_output, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         prediction1_val = sess.run(prediction, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         #accuracy_with_confusion_val = sess.run(accuracy_with_confusion, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         #something2 = sess.run(something, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         #b_val1 = sess.run(b, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         #kernel_val1 = sess.run(pred_kernel, feed_dict={x_data: rand_x, y_target: rand_y, prediction_grid: rand_x})
#         batch_accuracy.append(test_acc_temp)
#         i += 1
#     prediction_total.append(prediction1_val)
#     print('Total accuracy: \n' + str(float(sum(batch_accuracy)) / float(len(batch_accuracy))))
# 
# 
# =============================================================================