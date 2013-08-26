import logging
import os



class Logger():
    
    def log_data(self,log_file,info,_type):
        if os.path.exists(log_file) is False:
            try:
                _log = open(log_file, 'w+')
            except IOError,e:
                print "File Error %s" %e
                raise SystemExit 
            
        try:    
            logging.basicConfig(filename=log_file,format='%(asctime)s - %(levelname)s:%(message)s'
                                ,datefmt='%m/%d/%Y %I:%M:%S %p',level=logging.DEBUG)
            
            if type=="INFO":
                logging.info(info)
            
            elif type=="DEBUG":
                logging.debug(info)
        
            elif type=="ERROR":
                logging.error(info)
            
            elif type=="WARNING":
                logging.warning(info)
            else:
                logging.info(info)
                
        except IOError,e:
            print "Error, %s" %e
            raise SystemExit
            

            
        
        
        