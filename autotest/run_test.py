import os
import sys
import random
import string
import unicodedata
import time
import util
import novaaction
from write_to_csv import WriteCSV 
from util import GetConfig
from novaaction import NovaAction
from novaclient.v1_1 import client
from novaclient.exceptions import *
from config_data import GetVar
from util import GetConfig
import datetime
from random import randint


class TESTNOVA():
    
    def createConnection(self,_user,_key,_project_id,_auth_url):
        try:
            conn = client.Client(username=_user,api_key=_key,project_id=_project_id,auth_url=_auth_url)
            
        except Exception,e:
            return "Error %s" % e 
    
        return conn

        


    def TestBool(self,sent_stuff):
        
        var_test=1
        if sent_stuff=="ok":
            return True,sent_stuff,var_test
        else:
            return False,sent_stuff,var_test
        
        
        


__init__='main'



image_id='42857a50-0efe-4b80-b294-2f646cf4b061'
#vm_id='18d23802-14d4-4f87-a9b3-a68e90a86a08'
#vm_id='d9734166-5a02-464b-ae21-78c0a1622b37'





config = GetVar('nectar-test')
nov=NovaAction()
info = GetConfig() 
client= nov.createNovaConnection(config)
instances_id ='5aabab23-3974-47c3-8b06-d18e39d281a1'
count_limit=5
timeout=10
state='ACTIVE'
flavour_name='m1.tiny'
image_id=''
print client 


nov.getFlavour(flavour_name, client)
nov.getImageInfo(image_id, True, client)

#for i in range(1,100):
#    print "No:%r" % i
#    
#    print nov.getInstancesInfo(instances_id,client)[0].status
#    time.sleep(2)


'''
while nov.getImageInfo(image_id,False, client)==None:
    print "OK"
    time.sleep(5)
'''    
    

'''
print nov.deleteSnapshot(image_id, client)

print snap_image
try:
    snap_image.delete()
except Forbidden, e:
    print e
#remote_file='test-U0WKXO-290513150258'
#ssh_client = info.connectSSH('118.138.240.234','ec2-user','/tmp/.key_rc-U0WKXO-290513150258')
#cmd2="md5sum "+remote_file+" | cut -d' ' -f1"

#print "Value %s" % (info.runCommand(ssh_client,cmd=cmd2,_type=2))
#vm_id='77ae1ffa-d8fe-4aa8-89c4-f86cd2df130d'

#print info._pollStatus(config.timeout,vm_id,'ACTIVE',10,client)


#for i in range(5):
#    for i in client.images.list():
        #if i.id==unicode(image_id):
         #   print i    



#data1=nov.getInstancesInfo(instances_id,client)
#count_limit=5
#print info._pollInstancesTerminated(config.timeout,count_limit, vm_id, client)
#data=['1','2','3','4','5','6']
#print data
#write_data = WriteCSV().createCSVFile(config.csv_file,data)
#now = 

#print datetime.datetime.now().strftime("%d%m%y%H%M%S")
#print config.cp_file
#print info.sampleFile(config.cp_file)
 









print 

'''




'''
test_ = NovaAction()
client=test_.createNovaConnection(config)
test_.removeSecurityGroupRules(secure_group, client)
'''



'''
dict ={'sg':'xxxxx','keypair':'key'}



config = GetVar('deven')
images_test = NovaAction()
#image='b025abeb-d07c-4dfa-9b31-ad791203a101'

#results = images_test.getImageInfo(image,False, images_test.createNovaConnection(config))
#print results
#images_test.deleteSnapshot(image, images_test.createNovaConnection(config))
seg = '07DVXB-160513173723'
print images_test.getSecurityGroup(seg,images_test.createNovaConnection(config))


helper_ = GetConfig()
nova_action = NovaAction()

infra='preproduction'
username = helper_.process_config(infra,'user')
passwd = helper_.process_config(infra,'passwd')
name = helper_.process_config(infra,'name')
url = helper_.process_config(infra,'url')
image_id = helper_.process_config('image','image_id')
image_username = helper_.process_config('image','user_name')
work_directory = helper_.process_config('config','directory')
ssh_key_name = helper_.process_config('config','ssh_key_name') 
timeout = helper_.process_config('timeout','period')
flavour_name = helper_.process_config('flavour','flavour_type')
cp_file = helper_.process_config('file_check','local_file')
tmp_dir = helper_.process_config('file_check','tmp_dir')
cell = helper_.process_config('cell','location')
client = nova_action.createNovaConnection(username,passwd,name,url)
scheduler={'cell':cell}

ssh_key_name = work_directory+"/"+ssh_key_name
startTime = time.time()
test_name = helper_._randomName()
keypair = nova_action.createKeypair(test_name,client)

stat=helper_.writeFiles(ssh_key_name,keypair.private_key)

print "Test started at %r" % startTime 
if keypair!=None and stat==0:
    print "Keypair %s created" %test_name

security_group = nova_action.createSecurityGroup(test_name,client)
security_grouprules = nova_action.createSecurityGroupRules(security_group.id,'tcp','22','22',client)

print "Security %s Group Created" % security_group.name
print "Rules 'tcp', '22' 0.0.0.0/0 added"


flavour_info=nova_action.getFlavour(flavour_name,client)

print "Image %s " % image_id
print "Instances type %s" % flavour_info.name
print "Instances launching in 30 seconds"
time.sleep(20)
print "Running Instances "

run_instances = nova_action.runInstances(test_name,image_id,flavour_info.id,keypair.name,security_group.name.split(','),client,placement=scheduler)       

if run_instances!=None: 
    print "Instances launched Sucessfully"
else:
    print "Error Instances Failed to launch, Cleaning Up"

#poll the instances status until it becomes active
if helper_._pollStatus(timeout,run_instances.id,'ACTIVE',10,client)==True:
   vm_info = nova_action.getInstancesInfo(run_instances.id,client)
   print "Instances: %s, IP: %s, Status: %s" %(vm_info[0].name,vm_info[1][0],vm_info[0].status)
   print "Port 22 Test"
   if helper_.checkPortAlive(vm_info[1][0],int(timeout),22)==True:
       print "Port alive"
       print "Run File Check"
       time.sleep(10)
       if helper_.fileCheck(vm_info[1][0],image_username,cp_file,tmp_dir,ssh_key_name)==True:
           print "Check File ok"
           print "Reboot Server"
           nova_action.rebootInstances(vm_info[0])
           time.sleep(int(timeout))
           if helper_.checkPortAlive(vm_info[1][0],int(timeout),22)==True:
               print "Reboot OK"
               print "Run Snapshot"
               snapshot_ = nova_action.createSnapshot(test_name,vm_info[0].id,client)
               
               count=0
               while nova_action.getImageInfo(snapshot_,client)!='ACTIVE':
                   if count!=30:
                       
                       print nova_action.getImageInfo(snapshot_,client)
                
                       if nova_action.getImageInfo(snapshot_,client)!='ERROR':
                           time.sleep(10)
                           count=count+1
                           print count
                       elif nova_action.getImageInfo(snapshot_,client)==None:
                               print "Snapshot Failed, most likely killed"
                               raise SystemExit
                   else:
                        print "Snapshot failed, timeout after %s seconds" % (int(time.time()-startTime))
                        raise SystemExit
                        
                        
               print "Snapshot %s is ok," % snapshot_
               print "Test took %r seconds to finish" %  (int(time.time()-startTime))
               print "Launching VM from snapshot"
               run_snap = nova_action.runInstances("from-snap-"+test_name,snapshot_,flavour_info.id,keypair.name,security_group.name.split(','),client) 
             
                        
           else:
               print "Reboot Failed"
               raise SystemExit       
       else:
           print "Check File Failed"
           raise SystemExit
               
       
   else:
        print "Timeout from boot, it took %s seconds" %(time.time()- startTime)
        raise SystemExit
       
else:
    print "Timeout from build, stuck in %r for more than %r" % (run_instances.status, (time.time()-startTime)) 
    raise SystemExit    
    








#nova_action.deleteKeypair(keypair.name,client)
#helper_.removeFiles(work_directory+"/"+ssh_key_name)
#nova_action.removeSecurityGroupRules(security_group.id,client)

#vm_id='5888c8cc-d9f3-44d0-8aae-0c21650daec4'
#nova_action.deleteInstances(vm_id,client)
'''