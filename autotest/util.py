import os
import logging
import socket
import paramiko
import subprocess
import string
import random
import datetime
import time
from ConfigParser import SafeConfigParser
from paramiko import SSHClient, SSHConfig
from novaaction import NovaAction
from paramiko.ssh_exception import SSHException


class Alarm():
    pass

    def handler(self,signum,frame):
        raise Alarm()



class GetConfig():
    try:
        config_file = "/tmp/config.ini"
        with open(config_file):
            parser = SafeConfigParser()
            config_file = "/tmp/config.ini"
            parser.read(config_file)
    except IOError:
            print "Error!, Config File Not Found at (/tmp/config.ini)"
            raise SystemExit
    
    def process_config(self,section,option):
        for section_name in self.parser.sections():
            try:
                if section_name == section:
                    list_items = self.parser.get(section_name,option)
            except:
                list_items=None
                return list_items

        return list_items
    
    def port_test(self,host,timeout,port):
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, int(port)))
        except IOError,e:
            return e
        return 0
        
    def connectSSH(self,hostname,user,key_rc):
        #TODO, disable ssh logging by paramiko properly
        logging.getLogger("paramiko").setLevel(logging.WARNING)
        try: 
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(hostname, username=user, key_filename=key_rc)
            return ssh_client
        except SSHException:
            return False   
        
    

    def _randomName(self):
        now = datetime.datetime.now()
        char_set = string.ascii_uppercase + string.digits
        random_name =''.join(random.sample(char_set*6,6))+'-'+now.strftime("%d%m%y%H%M%S")
        return random_name
        
    
    def writeFiles(self,file_name,_info,mode=None):
        if os.path.exists(file_name):
            os.remove(file_name)
        try:
            file_open = open(file_name,"w")
            file_open.write(_info)
            if mode==None:
                os.chmod(file_name,0600)
            else:
                os.chmod(file_name,int(mode))
            
            file_open.close()
            return 0
        except IOError,e:
            return "Error",e
        
    def removeFiles(self,file_name):
        try:
            if os.path.exists(file_name):
                os.remove(file_name)
                return 0
            
        except IOError,e:
            return "Error",e
            
    
    def _pollStatus(self,timeout,poll_item,state,count_limit,client):
        count=0
        while NovaAction().getInstancesInfo(poll_item,client)[0].status!=state:
            if count!=count_limit:
                time.sleep(int(timeout))
                count=count+1
            else:
                return False
        return True
    
    def _pollTaskState(self,timeout,poll_item,count_limit,client):
        count=0
        while NovaAction().getInstancesInfo(poll_item,client)[0].status!='NULL':
            if count!=count_limit:
                time.sleep(int(timeout))
                count=count+1
            else:
                return False
        return True
    
    def _pollInstancesTerminated(self,timeout,count_limit,vm_id,client):
        count=0
        while NovaAction().getInstancesInfo(vm_id,client)!=None:
            if count!=count_limit:
                time.sleep(int(timeout))
                count=count+1
            else:
                return False
        return True
            
    def runCommand(self,ssh_session,cmd=None,_type=None,local_file=None):
        if _type==1:
            stdin, stdout, stderr = ssh_session.exec_command(cmd)
            return True
        elif _type==2:
            stdin, stdout, stderr = ssh_session.exec_command(cmd)
            _close = stdout.read()
            return _close
        elif _type==3:
            _scp=ssh_session.open_sftp()
            _scp.put(local_file,local_file.split('/')[2])
            _scp.close()
            return True
        elif _type==4:
            _scp=ssh_session.open_sftp()
            _scp.get(local_file.split('/')[2],local_file)
            _scp.close()
            return True           
        else:
            ssh_session.close()
            
           
    def fileCheck(self,ip_address,obj):
        
        remote_file = 'test-'+obj.test_name
        cmd1='dd if=/dev/zero of='+remote_file+' bs=1024K count=50'
        cmd2="md5sum "+remote_file+ " | cut -d' ' -f1"             
        ssh_session=self.connectSSH(ip_address, obj.image_username,obj.ssh_key)
        
        if ssh_session!=False:
            self.runCommand(ssh_session, cmd=cmd1,_type=1)
            time.sleep(10)
            check_sum = self.runCommand(ssh_session,cmd=cmd2,_type=2).rstrip("\n")

            self.runCommand(ssh_session,_type=3,local_file=obj.data_file)
            self.runCommand(ssh_session,_type=4,local_file=obj.tmp_dir+remote_file)
            
            _md5=subprocess.Popen(['md5sum',obj.tmp_dir+remote_file],shell=False,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            
            check_sum_local = _md5.communicate()[0].split()
        
            if str(check_sum)==str(check_sum_local[0]):
                if os.path.exists(obj.tmp_dir+"test-"+obj.test_name):
                    os.remove(obj.tmp_dir+"test-"+obj.test_name)
                return True
            else:
                if os.path.exists(obj.tmp_dir+"test-"+obj.test_name):
                    os.remove(obj.tmp_dir+"test-"+obj.test_name)
                return False
        else:
            return False
  
         
        
    def checkPortAlive(self,ip_address,timeout,port):
        count=0
        while self.port_test(ip_address,timeout,port)!=0:
            if count!=10:                
                time.sleep(timeout)
                count=count+1
            else:
                return False 
        return True
    
    def getrunTime(self,_type=None):
        
        if _type=='time':
            return time.time()
        else:
            return datetime.datetime.now().strftime("%d%m%y%H%M%S")
    
    
    def sampleFile(self,action,sample_file):
        if action=='create':
            try:
                out_fd = open(sample_file,'w+')
                cmd=['/usr/bin/head', '-c','2048000','/dev/urandom'] 
                run_cmd = subprocess.Popen(cmd,shell=False,stdout=out_fd,stderr=subprocess.PIPE)
                run_cmd.communicate()
                return True
            except IOError,e:
                print "Error, Unable to create data file to upload"
                raise SystemExit
        else:
            try:
                if os.path.exists(sample_file):
                    os.remove(sample_file)
            except IOError,e:
                return "Error",e 
        
        
        
        
         
         

