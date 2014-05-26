#============================================================#
#                                                            #
# $ID:$                                                      #
#                                                            #
# NaServer.py                                                #
#                                                            #
# Client-side interface to ONTAP and DataFabric Manager APIs.#
#                                                            #
# Copyright (c) 2011 NetApp, Inc. All rights reserved.       #
# Specifications subject to change without notice.           #
#                                                            #
#============================================================#

__version__ = "1.0"

from NaElement import *

import base64
import xml.parsers.expat
import socket

ssl_import = True
try:
    import ssl
except ImportError:
    ssl_import = False
    pass


python_version = float(str(sys.version_info[0]) + "." + str(sys.version_info[1]))

socket_ssl_attr = True
if(python_version < 3.0):
    import httplib
    if(hasattr(socket, 'ssl') != True):
        socket_ssl_attr = False
else :
    import http.client
    httplib = http.client
	
#dtd files
FILER_dtd = "file:/etc/netapp_filer.dtd"
DFM_dtd = "file:/etc/netapp_dfm.dtd"
AGENT_dtd = "file:/etc/netapp_agent.dtd"

#URLs
AGENT_URL = "/apis/XMLrequest"
FILER_URL = "/servlets/netapp.servlets.admin.XMLrequest_filer"
NETCACHE_URL = "/servlets/netapp.servlets.admin.XMLrequest"
DFM_URL = "/apis/XMLrequest"

ZAPI_xmlns = "http://www.netapp.com/filer/admin"

NMSDK_VERSION = "5.2.1"
NMSDK_LANGUAGE = "Python"
nmsdk_app_name = ""

class NaServer :
    """Class for managing Network Appliance(r) Storage System
    using ONTAPI(tm) and DataFabric Manager API(tm).

    An NaServer encapsulates an administrative connection to
    a NetApp Storage Systems running Data ONTAP 6.4 or later.
    NaServer can also be used to establish connection with
    OnCommand Unified Manager server (OCUM). You construct NaElement
    objects that represent queries or commands, and use invoke_elem()
    to send them to the storage systems or OCUM server. Also,
    a convenience routine called invoke() can be used to bypass
    the element construction step.  The return from the call is
    another NaElement which either has children containing the
    command results, or an error indication.

    The following routines are available for setting up
    administrative connections to a storage system or OCUM server.
    """



    def __init__(self, server, major_version, minor_version):
        """Create a new connection to server 'server'.  Before use,
    you either need to set the style to "hosts.equiv" or set
    the username (always "root" at present) and password with
    set_admin_user().
    """

        self.server = server
        self.major_version = major_version
        self.minor_version = minor_version
        self.transport_type = "HTTP"
        self.port = 80
        self.user = "root"
        self.password = ""
        self.style = "LOGIN"
        self.timeout = None
        self.vfiler = ""
        self.server_type = "FILER"
        self.debug_style = ""
        self.xml = ""
        self.originator_id = ""
        self.cert_file = None
        self.key_file = None
        self.ca_file = None
        self.need_cba = False;
        self.need_server_auth = False
        self.need_cn_verification = False
        self.url = FILER_URL
        self.dtd = FILER_dtd
        self.ZAPI_stack = []
        self.ZAPI_atts = {}



    def set_style(self, style):
        """Pass in 'LOGIN' to cause the server to use HTTP simple
    authentication with a username and password.  Pass in 'HOSTS'
    to use the hosts.equiv file on the filer to determine access
    rights (the username must be root in that case). Pass in
    'CERTIFICATE' to use certificate based authentication with the
    DataFabric Manager server.
    If style = CERTIFICATE, you can use certificates to authenticate
    clients who attempt to connect to a server without the need of
    username and password. This style will internally set the transport
    type to HTTPS. Verification of the server's certificate is required
    in order to properly authenticate the identity of the server.
    Server certificate verification will be enabled by default using this
    style and Server certificate verification will always enable hostname
    verification. You can disable server certificate (with hostname)
    verification using set_server_cert_verification().
    """

        if(style != "HOSTS" and style != "LOGIN" and style != "CERTIFICATE"):
            return self.fail_response(13001,"in NaServer::set_style: bad style \""+style+"\"")

        if (style == "CERTIFICATE") :
            if (ssl_import == False):
                return self.fail_response(13001,"in NaServer::set_style: \""+style+"\" cannot be used as 'ssl' module is not imported.")
            if (socket_ssl_attr == False):
                return self.fail_response(13001,"in NaServer::set_style: \""+style+"\" cannot be used as 'socket' module is not compiled with SSL support.")
            ret = self.set_transport_type("HTTPS")
            if (ret):
                return ret
            self.need_cba = True
            self.set_server_cert_verification(True)
        else :
            self.need_cba = False
            self.set_server_cert_verification(False)
        self.style = style
        return None



    def get_style(self):
        """Get the authentication style
    """

        return self.style



    def set_admin_user(self, user, password):
        """Set the admin username and password.  At present 'user' must
    always be 'root'.
    """

        self.user = user
        self.password = password



    def set_server_type(self, server_type):
        """Pass in one of these keywords: 'FILER' or 'DFM' or 'OCUM' to indicate
    whether the server is a storage system (filer) or a OCUM server.

    If you also use set_port(), call set_port() AFTER calling this routine.

    The default is 'FILER'.
    """

        if (server_type.lower() == 'filer'):
            self.url = FILER_URL
            self.dtd = FILER_dtd

        elif (server_type.lower() ==  'netcache'):
            self.url = NETCACHE_URL
            self.port = 80

        elif (server_type.lower() ==  'agent'):
            self.url = AGENT_URL
            self.port = 4092
            self.dtd = AGENT_dtd

        elif (server_type.lower() ==  'dfm'):
            self.url = DFM_URL
            self.port = 8088
            self.dtd = DFM_dtd

            if(self.transport_type == "HTTPS") :
                self.port = 8488

        elif (server_type.lower() ==  'ocum'):
            self.url = DFM_URL
            self.port = 443
            self.transport_type = "HTTPS"
            self.dtd = DFM_dtd


        else :
            return self.fail_response(13001,"in NaServer::set_server_type: bad type \""+server_type+"\"")

        self.server_type = server_type
        return None



    def get_server_type(self):
        """Get the type of server this server connection applies to.
    """

        return self.server_type



    def set_vserver(self, vserver):
        """Sets the vserver name. This function is added for vserver-tunneling.
    However, vserver tunneling actually uses vfiler-tunneling. Hence this
    function internally sets the vfiler name.
        """

        if(self.major_version >= 1 and self.minor_version >= 15):
            self.vfiler = vserver
            return 1

        print("\nONTAPI version must be at least 1.15 to send API to a vserver\n")
        return 0


    def get_vserver(self):
        """Gets the vserver name. This function is added for vserver-tunneling.
    However, vserver tunneling actually uses vfiler-tunneling. Hence this
    function actually returns the vfiler name.
        """

        return self.vfiler



    def set_originator_id(self, originator_id):
        """Function to set the originator_id before executing any ONTAP API.
        """

        self.originator_id = originator_id
        return 1


    def get_originator_id(self):
        """Gets the originator_id for the given server context on which the
    ONTAP API commands get invoked.
        """

        return self.originator_id



    def set_transport_type(self, scheme):
        """Override the default transport type.  The valid transport
    type are currently 'HTTP' and 'HTTPS'.
    """

        if(scheme != "HTTP" and scheme != "HTTPS"):
            return self.fail_response(13001,"in NaServer::set_transport_type: bad type \" "+scheme+"\"")

        if(scheme == "HTTP"):
            if(self.server_type == "OCUM"):
                return self.fail_response(13001,"Server type '" + self.server_type + "' does not support '" + scheme + "' transport type")

            self.transport_type = "HTTP"

            if(self.server_type == "DFM"):
                self.port = 8088

            else :
                self.port = 80


        if(scheme == "HTTPS"):
            if (socket_ssl_attr == False):
                return self.fail_response(13001,"in NaServer::set_transport_type: \""+scheme+"\" transport cannot be used as 'socket' module is not compiled with SSL support.")

            self.transport_type = "HTTPS"

            if(self.server_type == "DFM"):
                self.port = 8488

            else :
                self.port = 443

        return None



    def get_transport_type(self):
        """Retrieve the transport used for this connection.
    """

        return self.transport_type



    def set_debug_style(self, debug_style):
        """Set the style of debug.
    """

        if(debug_style != "NA_PRINT_DONT_PARSE"):
            return self.fail_response(13001,"in NaServer::set_debug_style: bad style \""+debug_style+"\"")

        else :
            self.debug_style = debug_style
            return



    def set_port(self, port):
        """Override the default port for this server.  If you
    also call set_server_type(), you must call it before
    calling set_port().
    """

        self.port = port



    def get_port(self):
        """Retrieve the port used for the remote server.
    """

        return self.port



    def is_debugging(self):
        """Check the type of debug style and return the
    value for different needs. Return 1 if debug style
    is NA_PRINT_DONT_PARSE,    else return 0.
    """

        if(self.debug_style == "NA_PRINT_DONT_PARSE"):
            return 1

        else :
            return 0



    def get_raw_xml_output(self):
        """Return the raw XML output.
    """

        return self.xml



    def set_raw_xml_output(self, xml):
        """Save the raw XML output.
    """

        self.xml = xml



    def use_https(self):
        """Determines whether https is enabled.
    """

        if(self.transport_type == "HTTPS"):
            return 1

        else :
            return 0



    def invoke_elem(self, req):
        """Submit an XML request already encapsulated as
        an NaElement and return the result in another
        NaElement.
        """
     
        server = self.server
        user = self.user
        password = self.password
        debug_style = self.debug_style
        vfiler = self.vfiler
        originator_id = self.originator_id
        server_type = self.server_type
        xmlrequest = req.toEncodedString()
        url = self.url
        vfiler_req = ""
        originator_id_req = ""
        nmsdk_app_req = ""

        try:

            if(self.transport_type == "HTTP"):
                    if(python_version < 2.6):  # python versions prior to 2.6 do not support 'timeout'
                        connection = httplib.HTTPConnection(server, port=self.port)
                    else :
                        connection = httplib.HTTPConnection(server, port=self.port, timeout=self.timeout)

            else : # for HTTPS

                    if (self.need_cba == True or self.need_server_auth == True):
                        if (python_version < 2.6):
                            cba_err = "certificate based authentication is not supported with Python " + str(python_version) + "." 
                            return self.fail_response(13001, cba_err) 
                        connection = CustomHTTPSConnection(server, self.port, key_file=self.key_file, 
                        cert_file=self.cert_file, ca_file=self.ca_file, 
                        need_server_auth=self.need_server_auth, 
                        need_cn_verification=self.need_cn_verification, 
                        timeout=self.timeout)
                        connection.connect()
                        if (self.need_cn_verification == True):
                            cn_name = connection.get_commonName()
                            if (cn_name.lower() != server.lower()) :
                                cert_err = "server certificate verification failed: server certificate name (CN=" + cn_name + "), hostname (" + server + ") mismatch."
                                connection.close()
                                return self.fail_response(13001, cert_err)
                    else :
                        if(python_version < 2.6): # python versions prior to 2.6 do not support 'timeout'
                            connection = httplib.HTTPSConnection(server, port=self.port)
                        else :
                            connection = httplib.HTTPSConnection(server, port=self.port, timeout=self.timeout)

            connection.putrequest("POST", self.url)
            connection.putheader("Content-type", "text/xml; charset=\"UTF-8\"")

            if(self.get_style() != "HOSTS"):

                if(python_version < 3.0):
                    base64string = base64.encodestring("%s:%s" %(user,password))[:-1]
                    authheader = "Basic %s" %base64string
                elif(python_version == 3.0):
                    base64string = base64.encodestring(('%s:%s' %( user, password)).encode())
                    authheader = "Basic %s" % base64string.decode().strip()
                else:
                    base64string = base64.encodebytes(('%s:%s' %( user, password)).encode())
                    authheader = "Basic %s" % base64string.decode().strip()

                connection.putheader("Authorization", authheader)

            if(vfiler != ""):
                vfiler_req = " vfiler=\"" + vfiler + "\""

            if(originator_id != ""):
                originator_id_req = " originator_id=\"" + originator_id + "\""

            if(nmsdk_app_name != ""):
                nmsdk_app_req = " nmsdk_app=\"" + nmsdk_app_name + "\"";

            content = '<?xml version=\'1.0\' encoding=\'utf-8\'?>'\
                     +'\n'+\
                     '<!DOCTYPE netapp SYSTEM \'' + self.dtd + '\''\
                     '>' \
                     '<netapp' \
                     + vfiler_req + originator_id_req + \
                     ' version="'+str(self.major_version)+'.'+str(self.minor_version)+'"'+' xmlns="' + ZAPI_xmlns  + "\"" \
                     + " nmsdk_version=\"" + NMSDK_VERSION + "\"" \
                     + " nmsdk_platform=\"" + NMSDK_PLATFORM + "\"" \
                     + " nmsdk_language=\"" + NMSDK_LANGUAGE + "\"" \
                     + nmsdk_app_req \
                     + ">" \
                     + xmlrequest + '</netapp>'

            if(debug_style == "NA_PRINT_DONT_PARSE"):
                print(("INPUT \n" +content))

            if(python_version < 3.0):
                connection.putheader("Content-length", len(content))
                connection.endheaders()
                connection.send(content)
            else :
                connection.putheader("Content-length", str(len(content)))
                connection.endheaders()
                connection.send(content.encode())


        except socket.error :
            message = sys.exc_info()
            return (self.fail_response(13001, message[1]))

        response = connection.getresponse()
    
        if not response :
            connection.close()
            return self.fail_response(13001,"No response received")

        if(response.status == 401):
            connection.close()
            return self.fail_response(13002,"Authorization failed")

        xml_response = response.read()

        if(self.is_debugging() > 0):

            if(debug_style != "NA_PRINT_DONT_PARSE"):
                self.set_raw_xml_output(xml_response)
                print(("\nOUTPUT :",xml_response,"\n"))
                connection.close()
                return self.fail_response(13001, "debugging bypassed xml parsing")
        
        connection.close()
        return self.parse_xml(xml_response)



    def invoke(self, api, *arg):
        """A convenience routine which wraps invoke_elem().
    It constructs an NaElement with name $api, and for
    each argument name/value pair, adds a child element
    to it.  It's an error to have an even number of
    arguments to this function.

    Example: myserver->invoke('snapshot-create',
                                    'snapshot', 'mysnapshot',
                                'volume', 'vol0');
    """

        num_parms = len(arg)

        if ((num_parms & 1)!= 0):
            return self.fail_response(13001,"in Zapi::invoke, invalid number of parameters")

        xi = NaElement(api)
        i = 0

        while(i < num_parms):
            key = arg[i]
            i = i+1
            value = arg[i]
            i = i+1
            xi.child_add(NaElement(key, value))

        return self.invoke_elem(xi)



    def set_vfiler(self, vfiler_name):
        """Sets the vfiler name. This function is used
    for vfiler-tunneling.
    """

        if(self.major_version >= 1 and self.minor_version >= 7 ):
                self.vfiler = vfiler_name
                return 1

        return 0


    def set_timeout(self, timeout):
        """Sets the connection timeout value, in seconds,
    for the given server context.
    """

        if (python_version < 2.6):
            print("\nPython versions prior to 2.6 do not support timeout.\n")
            return
        self.timeout = timeout



    def get_timeout(self):
        """Retrieves the connection timeout value (in seconds)
    for the given server context.
    """

        return self.timeout

    def set_client_cert_and_key(self, cert_file, key_file):
        """ Sets the client certificate and key files that are required for client authentication
        by the server using certificates. If key file is not defined, then the certificate file 
        will be used as the key file.
        """

        self.cert_file = cert_file
        if (key_file != None):
            self.key_file = key_file
        else:
            self.key_file = cert_file

    def set_ca_certs(self, ca_file):
        """ Specifies the certificates of the Certificate Authorities (CAs) that are 
        trusted by this application and that will be used to verify the server certificate.
        """

        self.ca_file = ca_file

    def set_server_cert_verification(self, enable):
        """ Enables or disables server certificate verification by the client.
        Server certificate verification is enabled by default when style 
        is set to CERTIFICATE. Hostname (CN) verification is enabled 
        during server certificate verification. Hostname verification can be 
        disabled using set_hostname_verification() API.
        """

        if (enable != True and enable != False):
            return self.fail_response(13001, "NaServer::set_server_cert_verification: invalid argument " + str(enable) + " specified");
        if (not self.use_https()):
            return self.fail_response(13001,"in NaServer::set_server_cert_verification: server certificate verification can only be enabled or disabled for HTTPS transport")
        if (enable == True and ssl_import == False):
            return self.fail_response(13001,"in NaServer::set_server_cert_verification: server certificate verification cannot be used as 'ssl' module is not imported.")
        self.need_server_auth = enable
        self.need_cn_verification = enable
        return None

    def is_server_cert_verification_enabled(self):
        """ Determines whether server certificate verification is enabled or not.
        Returns True if it is enabled, else returns False
        """

        return self.need_server_auth

    def set_hostname_verification(self, enable):
        """  Enables or disables hostname verification during server certificate verification.
        Hostname (CN) verification is enabled by default during server certificate verification. 
        """

        if (enable != True and enable != False):
            return self.fail_response(13001, "NaServer::set_hostname_verification: invalid argument " + str(enable) + " specified")
        if (self.need_server_auth == False):
            return self.fail_response(13001, "in NaServer::set_hostname_verification: server certificate verification is not enabled")
        self.need_cn_verification = enable
        return None;

    def is_hostname_verification_enabled(self):
        """ Determines whether hostname verification is enabled or not.
        Returns True if it is enabled, else returns False
        """

        return self.need_cn_verification;

    ## "private" subroutines for use by the public routines


    ## This is used when the transmission path fails, and we don't actually
    ## get back any XML from the server.
    def fail_response(self, errno, reason):
        """This is a private function, not to be called from outside NaElement
        """
        n = NaElement("results")
        n.attr_set("status","failed")
        n.attr_set("reason",reason)
        n.attr_set("errno",errno)
        return n



    def start_element(self, name, attrs):
        """This is a private function, not to be called from outside NaElement
        """

        n = NaElement(name)
        self.ZAPI_stack.append(n)
        self.ZAPI_atts = {}
        attr_name = list(attrs.keys())
        attr_value = list(attrs.values())
        i = 0
        for att in attr_name :
            val = attr_value[i]
            i = i+1
            self.ZAPI_atts[att] = val
            n.attr_set(att,val)



    def end_element(self, name):
        """This is a private function, not to be called from outside NaElement
        """

        stack_len = len(self.ZAPI_stack)

        if (stack_len > 1):
            n = self.ZAPI_stack.pop(stack_len - 1)
            i = len(self.ZAPI_stack)

            if(i != stack_len - 1):
                print("pop did not work!!!!\n")

            self.ZAPI_stack[i-1].child_add(n)



    def char_data(self, data):
        """This is a private function, not to be called from outside NaElement
        """

        i = len(self.ZAPI_stack)
        data = NaElement.escapeHTML(data)
        self.ZAPI_stack[i-1].add_content(data)



    def parse_xml(self, xmlresponse):
        """This is a private function, not to be called from outside NaElement
        """
        p = xml.parsers.expat.ParserCreate()
        p.StartElementHandler = self.start_element
        p.EndElementHandler = self.end_element
        p.CharacterDataHandler = self.char_data
        p.Parse(xmlresponse, 1)
        stack_len = len(self.ZAPI_stack)

        if(stack_len <= 0):
            return self.fail_response(13001,"Zapi::parse_xml-no elements on stack")

        r = self.ZAPI_stack.pop(stack_len - 1)

        if (r.element['name'] != "netapp") :
            return self.fail_response(13001, "Zapi::parse_xml - Expected <netapp> element but got " + r.element['name'])

        results = r.child_get("results")

        if (results == None) :
            return self.fail_response(13001, "Zapi::parse_xml - No results element in output!")

        return results



    def parse_raw_xml(self, xmlrequest):
        """This is a private function, not to be called from outside NaElement
        """

        p = xml.parsers.expat.ParserCreate()
        p.StartElementHandler = self.start_element
        p.EndElementHandler = self.end_element
        p.CharacterDataHandler = self.char_data
        p.Parse(xmlrequest,1)
        stack_len = len(self.ZAPI_stack)

        if(stack_len <= 0):
            return self.fail_response(13001,"Zapi::parse_xml-no elements on stack")

        r = self.ZAPI_stack.pop(stack_len - 1)

        return r


    @staticmethod
    def set_application_name (app_name):
        """ Sets the name of the client application.
        """

        global nmsdk_app_name
        nmsdk_app_name = app_name

    @staticmethod
    def get_application_name ():
        """ Returns the name of the client application.
        """

        global nmsdk_app_name
        return nmsdk_app_name


    @staticmethod
    def get_platform_info():
        """ Returns the platform information.
        """

        systemType = "Unknown"
        osName = ""
        processor = ""
        osInfo = ""

        try:
            import platform
            systemType = platform.system()
            if (systemType == "Windows" or systemType == "Microsoft"):
                systemType = "Windows"
                if(python_version < 3.0):
                    import _winreg
                    handle = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion")
                    (osName, type) = _winreg.QueryValueEx(handle, "ProductName")
                    _winreg.CloseKey(handle)
                    handle = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "SYSTEM\\ControlSet001\\Control\\Session Manager\\Environment")
                    (processor, type) = _winreg.QueryValueEx(handle, "PROCESSOR_ARCHITECTURE")
                    _winreg.CloseKey(handle)
                else:
                    import winreg
                    handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion")
                    (osName, type) = winreg.QueryValueEx(handle, "ProductName")
                    winreg.CloseKey(handle)
                    handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SYSTEM\\ControlSet001\\Control\\Session Manager\\Environment")
                    (processor, type) = winreg.QueryValueEx(handle, "PROCESSOR_ARCHITECTURE")
                    winreg.CloseKey(handle)
                osInfo = osName + " " + processor
            else:
                import os
                if (systemType == "Linux"):
                    import re
                    pipe = ""
                    if os.path.isfile("/etc/SuSE-release"):
                        pipe = os.popen('head -n 1 /etc/SuSE-release')
                    else:
                        pipe = os.popen("head -n 1 /etc/issue")
                    osName = pipe.readline()
                    pipe.close()
                    osName = osName.rstrip()
                    m = re.search("(.*?) \(.*?\)", osName)
                    if m:
                        osName = m.groups()[0]
                    pipe = os.popen('uname -p')
                    processor = pipe.readline()
                    pipe.close()
                    processor = processor.rstrip()
                    osInfo = osName + " " + processor
                elif (systemType == 'SunOS'):
                    pipe = os.popen('uname -srp')
                    unameInfo = pipe.readline()
                    pipe.close()
                    unameInfo = unameInfo.rstrip()
                    pipe = os.popen('isainfo -b')
                    isaInfo = pipe.readline()
                    pipe.close()
                    isaInfo = isaInfo.rstrip()
                    isaInfo += "-bit"
                    osInfo = unameInfo + " " + isaInfo
                elif (systemType == 'HP-UX'):
                    pipe = os.popen('uname -srm')
                    osInfo = pipe.readline()
                    pipe.close()
                    osInfo = osInfo.rstrip()
                elif (systemType == 'FreeBSD'):
                    pipe = os.popen('uname -srm')
                    osInfo = pipe.readline()
                    pipe.close()
                    osInfo = osInfo.rstrip()
                else:
                    osInfo = systemType
        except:
            osInfo = systemType
        return osInfo

NMSDK_PLATFORM = NaServer.get_platform_info()

try:
    class CustomHTTPSConnection(httplib.HTTPSConnection):
        """ Custom class to make a HTTPS connection, with support for Certificate Based Authentication"""

        def __init__(self, host, port, key_file, cert_file, ca_file, 
                   need_server_auth, need_cn_verification, timeout=None):
            httplib.HTTPSConnection.__init__(self, host, port=port, key_file=key_file, 
                                     cert_file=cert_file,timeout=timeout)
            self.key_file = key_file
            self.cert_file = cert_file
            self.ca_file = ca_file
            self.timeout = timeout
            self.need_server_auth = need_server_auth
            self.need_cn_verification = need_cn_verification

        def connect(self):
            sock = socket.create_connection((self.host, self.port), self.timeout)

            if (self.need_server_auth == True):
                self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ca_certs=self.ca_file, cert_reqs=ssl.CERT_REQUIRED)
            else:
                self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ca_certs=self.ca_file)

        def get_commonName(self):
            cert = self.sock.getpeercert()
            for x in cert['subject'] :
                if (x[0][0].lower() == 'commonname') :
                    return x[0][1]
            return ""
except AttributeError:
    pass




