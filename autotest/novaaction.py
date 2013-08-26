import sys
import locale
import time
from novaclient.v1_1 import client
from novaclient.exceptions import *



class NovaAction():
    def createNovaConnection(self,obj):
        
            try:
                conn = client.Client(username=obj.username,api_key=obj.passwd,project_id=obj.name,auth_url=obj.url)
                return conn
  
            except ClientException:
                return False
    
    def createKeypair(self,name,client):
        pub_key = None
        keypair = client.keypairs.create(name,pub_key)
        return keypair
    
    def createSecurityGroup(self,name,client):
        description = 'security group for test '+name
        try:
            security_group = client.security_groups.create(name,description)
            return security_group
        except OverLimit:
            return False
        
    def createSecurityGroupRules(self,sg_id,proto,port_to,port_frm,client):
        security_grouprules = client.security_group_rules.create(sg_id,proto,port_to,port_frm)
        return security_grouprules
 
    def getImageInfo(self,image_id,type_,client):
        
        count=0
        while count!=5:
            try: 
                for i in client.images.list():
                    if i.id==unicode(image_id):
                        if i!=None:
                            if type_==True:
                                return i.status 
                            elif type_==False: 
                                return i
                            else:
                                return 0
            except Exception,ClientException:
                count=count+1
        
        return False
        
    def getFlavour(self,flavour_name,client):
        for i in client.flavors.list():
            if i.name==unicode(flavour_name):
                if i!=None:
                    return i
                else:
                    return 1
    def getSecurityGroup(self,name,client):
        
        grp_name=None
        
        for sg in client.security_groups.list():
            
            encoding = (locale.getpreferredencoding() or
            sys.stdin.encoding or
            'UTF-8')
            sg.name = sg.name.encode(encoding)
            if name==sg.name:
                grp_name=sg.id
            
        return grp_name
                
        
    def runInstances(self,name,image_id,flavor,keypair_name,sg_name,client,user_data=None,placement=None):
        hints={'cell':placement}
        if user_data==None:
            run_instances = client.servers.create(name,image_id,flavor,key_name=keypair_name,
                                              security_groups=sg_name,scheduler_hints=hints)
            return run_instances
    def rebootInstances(self,vm):
        if vm.reboot():
            return True
    def createSnapshot(self,name,vm_id,client):
        try:
            snapshot_id=client.servers.create_image(vm_id,"snap-"+name)
            return snapshot_id
        except ClientException:
            return False
               
                
    def getInstancesInfo(self,vm_id,client):
            vm_ip=""
            ip_address=[]
            for i in client.servers.list():
                if i.id==unicode(vm_id):
                    for network_label,address_list in i.networks.items():
                        if address_list!=None or address_list=="":
                            vm_ip="".join(address_list)
                            ip_address.append(vm_ip)
                      
                        
                    return i,ip_address
                
                
    def terminateInstances(self,vm_id,client):
            client.servers.delete(vm_id)
            return True
        
        
        
    def deleteSnapshot(self,snapshot,client):
        
        count = 0 
        if count!=10:
            image = self.getImageInfo(snapshot,False,client)
            if image!=False:
                while True:
                    try:
                        image.delete()
                        return True
                    except Forbidden:
                        return False
                    except ClientException:
                        count=count+1
            else:
                count=count+1
        else:
            return False
                

                
            
    def removeSecurityGroupRules(self,sg_name,client):
            count =0

            if count!=10:
                sg_id = self.getSecurityGroup(sg_name,client)
                if sg_id!=None:
                    while True or count!=10:
                        try:
                            client.security_groups.delete(sg_id)
                            return True
                        except BadRequest:
                            time.sleep(10)
                            count=count+1
                else:
                    count=count+1
            else:
                return False

            
                
    
    def deleteKeypair(self,name,client):
        client.keypairs.delete(name)
        return True
        
         
            
            

        
                                             
 

                
        
        
        
        
