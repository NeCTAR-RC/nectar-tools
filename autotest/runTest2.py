import time
import datetime
from util import GetConfig
from runtestinstances import RunInstancesTest
from logger import Logger
from cleanup import CleanUp
from write_to_csv import WriteCSV

class RunTest2():
    
   
    
    var_ = GetConfig()
    log = Logger()
    test = RunInstancesTest()
    clear = CleanUp()
    writer_ = WriteCSV()
    startTime = time.time()
    run_time = datetime.datetime.now().strftime("%d%m%y%H%M%S")
    def runTest2(self,config):
        
        
        print "Running Instances Test:%s on cell %r" % (config.test_name,config.cell)
        if self.test.preTestCheck(config)!=False:
            msg = "Pre Check passed, running instances test"
            self.log.log_data(config.log_file,msg,"INFO")
            run_result = self.test.runTest(config)
            if run_result[0]!=False:
                msg = "Instances test passed"
                self.log.log_data(config.log_file,msg,"INFO")
                print msg
            
                msg = "Running Cleaning up"
                self.log.log_data(config.log_file,msg,"INFO")
                print msg
            
                msg = "Terminating Instances"
                self.log.log_data(config.log_file,msg,"INFO")
                print msg
                self.clear.removeInstances(config, run_result[1])
                
                msg = "Removing security group and key pair"
                self.log.log_data(config.log_file,msg,"INFO")
                misc = {'sg':config.test_name,'kp':config.test_name}
                
                if self.clear.removeMisc(config,misc,run_result[1])==True:
                    time_comp = time.time()-self.startTime
                    msg = "Clean Up complete, exiting test"
                    self.log.log_data(config.log_file,msg,"INFO")
                
                    print msg  
                    data_insert = [config.test_name,self.run_time,config.cell,run_result[2],'P','NA','NA',time_comp,'P']
                    WriteCSV().createCSVFile(config.csv_file, data_insert)
                    raise SystemExit
                else:
                    time_comp = time.time()-self.startTime
                    msg = "Error, Unable to remove security group and key pair"
                    self.log.log_data(config.log_file,msg,"ERROR")
                    print msg
                    data_insert = [config.test_name,self.run_time,config.cell,run_result[2],'P','NA','NA',time_comp,'F']
                    WriteCSV().createCSVFile(config.csv_file, data_insert)
                    raise SystemExit
            else:
                msg = "Run instances test failed"
                self.log.log_data(config.log_file,msg,"ERROR")
                print msg
           
            
                msg = "Running Cleaning up"
                self.log.log_data(config.log_file,msg,"INFO")
                print msg
                
                msg = "Terminating Instances"
                self.log.log_data(config.log_file,msg,"INFO")
                print msg
                self.clear.removeInstances(config, run_result[1])
                
                msg = "Removing Security Groups and Keypair"
                self.log.log_data(config.log_file,msg,"INFO")
                misc = {'sg':config.test_name,'kp':config.test_name}
                if self.clear.removeMisc(config,misc,run_result[1])==True:
                    time_comp = time.time()-self.startTime
                    data_insert = [config.test_name,self.run_time,config.cell,run_result[2],run_result[3],'NA','NA',time_comp,'F']
                    WriteCSV().createCSVFile(config.csv_file, data_insert)
                    msg = "Clean Up complete, exiting test"
                    self.log.log_data(config.log_file,msg,"INFO")
                else:
                    time_comp = time.time()-self.startTime
                    msg = "Error, Unable to remove security group and key pair"
                    self.log.log_data(config.log_file,msg,"ERROR")
                    print msg
                    data_insert = [config.test_name,self.run_time,config.cell,run_result[2],run_result[3],'NA','NA',time_comp,'F']
                    WriteCSV().createCSVFile(config.csv_file, data_insert)
                    raise SystemExit
                    
        
        else:
            msg = "Pre Check failed,test halted"
            self.log.log_data(config.log_file,msg,"ERROR")
            time_comp = self.var_.getrunTime('start')-self.var_.getrunTime(type)
            data_insert = [config.test_name,self.run_time,config.cell,'NA','FPCT','NA','NA',time_comp,'F']
            WriteCSV().createCSVFile(config.csv_file, data_insert)
            print msg
            raise SystemExit
            
            
