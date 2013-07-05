import os
import sys
import csv

class WriteCSV():
    
    def createCSVFile(self,filename,data):
        
   
        if os.path.exists(filename) is False:
            try:
                record = open(filename, 'w+')
                writer = csv.writer(record,delimiter=',',quoting=csv.QUOTE_ALL)
                writer.writerow(['TestId','DATETIME','CELL','VMRUN','RUN_STAT','SNAPRUN','SNAP_STAT','OVERALL','OVERA_STAT'])
                writer.writerow([data[0],data[1],data[2],data[3],data[4],data[5],data[6],data[7],data[8]])
               
            except IOError,e:
                print "File Error" %e
                raise SystemExit
        else:
            with open(filename,'a') as w:
                writer = csv.writer(w,delimiter=',',quoting=csv.QUOTE_ALL)
                writer.writerow([data[0],data[1],data[2],data[3],data[4],data[5],data[6],data[7],data[8]])
    

        

        
        
