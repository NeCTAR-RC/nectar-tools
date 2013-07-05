import time
from util import GetConfig
from novaaction import NovaAction
from logger import Logger



class RunInstancesTest():
    nova_ = NovaAction()
    log = Logger()
    helper = GetConfig()
        
    
    def preTestCheck(self,obj):
        
        
        client = self.nova_.createNovaConnection(obj)
        image_status = self.nova_.getImageInfo(obj.image_id,False,client)
        flavour_info = self.nova_.getFlavour(obj.flavour_name,client)
        data_file = self.helper.sampleFile('create', obj.data_file)
        
        if image_status!=None and flavour_info!=None and data_file==True:
            msg="Image: %s (%s), status: %s" % (image_status.name,image_status.id, image_status.status)
            self.log.log_data(obj.log_file,msg,"INFO")
            msg="Flavour type: %s, Flavour id: %s" %(flavour_info.name,flavour_info.id)
            self.log.log_data(obj.log_file,msg,"INFO")
            return True
        else:
            msg="Pre-flight check test failed! Image Status:%s ,Flavour Status: %s , Data File %s,  exiting test " % (image_status,flavour_info,data_file)
            self.log.log_data(obj.log_file,msg,"ERROR")
            self.helper.sampleFile('remove',obj.data_file)
            return False
        
  

    def runTest(self,obj):
        
        startTime = time.time()
        
     
        client = self.nova_.createNovaConnection(obj)
        
        
        msg="Instance Run Test %s started" % obj.test_name
        self.log.log_data(obj.log_file,msg,"INFO")
        
        keypair = self.nova_.createKeypair(obj.test_name,client)
        msg="Keypair created"
        self.log.log_data(obj.log_file,msg,"INFO")
        
        
        stat = self.helper.writeFiles(obj.ssh_key,keypair.private_key)
        msg="SSH key written to file"
        self.log.log_data(obj.log_file,msg,"INFO")
        
        if keypair!=None and stat==0:
            msg = "Keypair %s created" %obj.test_name
            self.log.log_data(obj.log_file,msg,"INFO")
        else:
            msg = "Error in generating keypair"
            self.log.log_data(obj.log_file,msg,"ERROR")
            return False,None,(time.time()-startTime),"FKP"
        
        security_group = self.nova_.createSecurityGroup(obj.test_name,client)
        if security_group!=False:
            msg = "Security Group %s created" % security_group.name
            self.log.log_data(obj.log_file,msg,"INFO")
        else:
            msg = "Fail to create Security Group"
            self.log.log_data(obj.log_file,msg,"INFO")
            return False,None,(time.time()-startTime),"FSG"
            
        
        self.nova_.createSecurityGroupRules(security_group.id,'tcp','22','22',client)
        msg = "Rules 'tcp', '22' 0.0.0.0/0 added"
        self.log.log_data(obj.log_file,msg,"INFO")
        time.sleep(int(obj.timeout))
        
        
        flavour_info = self.nova_.getFlavour(obj.flavour_name,client)
        
        msg = "Launching instances in 10 seconds"
        self.log.log_data(obj.log_file,msg,"INFO")
        
       
        run_instances = self.nova_.runInstances(obj.test_name,obj.image_id,flavour_info.id,keypair.name,security_group.name.split(','),client,placement=obj.cell)
        
        if run_instances!=None:
             
            msg = "Instances launched, ID returned as %s" % run_instances.id
            self.log.log_data(obj.log_file,msg,"INFO")
            
        else:
            msg = "Failed to launch instances"
            self.log.log_data(obj.log_file,msg,"ERROR")
            return False,None,(time.time()-startTime),"FRI"
        
        if self.helper._pollStatus(obj.timeout,run_instances.id,'ACTIVE',10,client)==True:
            vm_post_run = self.nova_.getInstancesInfo(run_instances.id,client) 
            msg = "Instances: %s, IP: %s, Status: %s" % (vm_post_run[0].name,vm_post_run[1][0],vm_post_run[0].status)
            self.log.log_data(obj.log_file,msg,"INFO")
            
            if self.helper.checkPortAlive(vm_post_run[1][0],int(obj.timeout),22)==True:
                msg = "Port is up and responding, proceeding to run file check in the next 10 seconds"
                self.log.log_data(obj.log_file,msg,"INFO")
                time.sleep(int(obj.timeout))
                
                msg = "Running file check"
                self.log.log_data(obj.log_file,msg,"INFO")
              
                if self.helper.fileCheck(vm_post_run[1][0],obj)==True:
                    msg = "File Check completed...passed"
                    self.log.log_data(obj.log_file,msg,"INFO")
                    
                    msg = "Rebooting instances"
                    self.log.log_data(obj.log_file,msg,"INFO")
                    self.nova_.rebootInstances(vm_post_run[0])
                    
                    if self.helper._pollStatus(obj.timeout,run_instances.id,'ACTIVE',10,client)==True:
                        
                        if self.helper.checkPortAlive(vm_post_run[1][0],int(obj.timeout),22)==True:

                            msg = "Reboot OK"
                            self.log.log_data(obj.log_file,msg,"INFO")
                            print msg
                            return True,vm_post_run[0],(time.time()-startTime)
                    
                        else:
                            msg = "Reboot Failed, Exiting Test"
                            self.log.log_data(obj.log_file,msg,"ERROR")
                            print msg
                            return False,vm_post_run[0],(time.time()-startTime),"FRI"
                    else:
                        msg = "Task state did not change, stuck in reboot"
                        self.log.log_data(obj.log_file,msg,"ERROR")
                        print msg
                        return False,vm_post_run[0],(time.time()-startTime),"FRTS"
                        
                    
                
                else:
                    msg = "File Check failed, exiting  Test"
                    self.log.log_data(obj.log_file,msg,"ERROR")
                    print msg
                    return False,vm_post_run[0],(time.time()-startTime),"FFT"
                    
            
            
            else:
                msg = "Port is not responding after %.2f, possible timeout from boot" % (time.time()- startTime)
                self.log.log_data(obj.log_file,msg,"ERROR")
                print msg
                return False,vm_post_run[0],(time.time()- startTime),"FIPN"
                
            
            
        else:
            vm_post_run = self.nova_.getInstancesInfo(run_instances.id,client)
            msg = "Timeout from build, stuck in %r for more than %.2f" % (run_instances.status, (time.time()-startTime))
            self.log.log_data(obj.log_file,msg,"ERROR") 
            print msg
            return False,vm_post_run[0],(time.time()- startTime),"FISB"
              
    
