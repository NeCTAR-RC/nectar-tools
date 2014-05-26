#============================================================#
#                                                            #
# $ID$                                                       #
#                                                            #
# NaElement.py                                               #
#                                                            #
# Operations on ONTAPI and DataFabric Manager elements       #
#                                                            #
# Copyright (c) 2011 NetApp, Inc. All rights reserved.       #
# Specifications subject to change without notice.           #
#                                                            #
#============================================================#

__version__ = 1.0


import re
import sys

class NaElement :
    """Class encapsulating Netapp XML request elements.

    An NaElement encapsulates one level of an XML element.
    Elements can be arbitrarily nested.  They have names,
    corresponding to XML tags, attributes (only used for
    results), values (always strings) and possibly children,
    corresponding to nested tagged items.  See NaServer for
    instructions on using NaElements to invoke ONTAPI API calls.

    The following routines are available for constructing and
    accessing the contents of NaElements.
    """ 


    #Global Variables
    DEFAULT_KEY = "#u82fyi8S5\017pPemw"
    MAX_CHUNK_SIZE = 256


    def __init__(self, name, value=None):
        """Construct a new NaElement.  The 'value' parameter is
        optional for top level elements.
        """ 

        self.element = {'name':name,'content':"",'children':[],'attrkeys':[],'attrvals':[]}
        if (value != None) :
            self.element['content'] = value


    def results_status(self) :
        """Indicates success or failure of API call.
        Returns either 'passed' or 'failed'.
        """ 
        r = self.attr_get("status")

        if(r == "passed"):
            return "passed"

        else :
            return "failed"


    def results_reason(self):
        """Human-readable string describing a failure.
        Only present if results_status does not return 'passed'.
        """ 

        r = self.attr_get("status")
        if(r == "passed"):
            return None

        r = self.attr_get("reason")
        if not r:
            return "No reason given"

        return str(r)


    def results_errno(self):
        """Returns an error number, 0 on success.
        """ 

        r = self.attr_get("status")

        if (r == "passed"):
            return 0

        r = self.attr_get("errno")

        if not r:
            r = -1

        return r


    def child_get(self, name):
        """Get a named child of an element, which is also an
        element.  Elements can be nested arbitrarily, so
        the element you get with this could also have other
        children.  The return is either an NaElement named
        'name', or None if none is found.
        """ 

        arr = self.element['children']

        for i in arr :

            if(name == i.element['name']):
                return i

        return None


    def set_content(self, content):
        """Set the element's value to 'content'.  This is
        not needed in normal development.
        """ 

        self.element['content'] = content


    def add_content(self, content):
        """Add the element's value to 'content'.  This is
        not needed in normal development.
        """ 

        self.element['content'] = self.element['content']+content
        return



    def has_children(self):
        """Returns 1 if the element has any children, 0 otherwise
        """ 

        arr = self.element['children']

        if(len(arr)>0):
            return 1

        else :
            return 0



    def child_add(self, child):
        """Add the element 'child' to the children list of
        the current object, which is also an element.
        """ 

        arr = self.element['children']
        arr.append(child)
        self.element['children'] = arr



    def child_add_string(self, name, value):
        """Construct an element with name 'name' and contents
        'value', and add it to the current object, which
        is also an element.
        """ 

        elt = NaElement(name,value)
        self.child_add(elt)



    def child_get_string(self, name):
        """Gets the child named 'name' from the current object
        and returns its value.  If no child named 'name' is
        found, returns None.
        """ 

        elts = self.element['children']

        for elt in elts:
            if (name == elt.element['name']):
                return elt.element['content']

        return None



    def child_get_int(self, child):
        """Gets the child named 'name' from the current object
        and returns its value as an integer.  If no child
        named 'name' is found, returns None.
        """ 

        temp =  self.child_get_string(child)
        return int(temp)



    def children_get(self):
        """Returns the list of children as an array.
        """ 

        elts = self.element['children']
        return elts



    def sprintf(self, indent=""):
        """Sprintf pretty-prints the element and its children,
        recursively, in XML-ish format.  This is of use
        mainly in exploratory and utility programs.  Use
        child_get_string() to dig values out of a top-level
        element's children.

        Parameter 'indent' is optional.
        """ 

        name = self.element['name']
        s = indent+"<"+name
        keys = self.element['attrkeys']
        vals = self.element['attrvals']
        j = 0

        for i in keys:
            s = s+" "+str(i)+"=\""+str(vals[j])+"\""
            j = j+1

        s = s+">"
        children = self.element['children']

        if(len(children) > 0):
            s = s+"\n"

        for i in children:
            c = i

            if (not re.search('NaElement.NaElement', str(c.__class__), re.I)):
                sys.exit("Unexpected reference found, expected NaElement.NaElement not "+ str(c.__class__)+"\n")

            s = s+c.sprintf(indent + "\t")

        self.element['content'] = NaElement.escapeHTML(self.element['content'])
        s = s + str(self.element['content'])

        if(len(children) > 0):
            s = s+indent

        s = s+"</"+name+">\n"
        return s



    def child_add_string_encrypted(self, name, value, key=None):
        """Same as child_add_string, but encrypts 'value'
        with 'key' before adding the element to the current
        object.  This is only used at present for certain
        key exchange operations.  Both client and server
        must know the value of 'key' and agree to use this
        routine and its companion, child_get_string_encrypted().
        The default key will be used if the given key is None.
        """ 

        if(not name or not value):
            sys.exit("Invalid input specified for name or value")

        if (key == None):
            key = self.DEFAULT_KEY

        if (len(key) != 16):
            sys.exit("Invalid key, key length sholud be 16")

        #encryption of key and others
        encrypted_value = self.RC4(key,value)
        self.child_add_string(name,unpack('H*',encrypted_value))



    def child_get_string_encrypted(self, name, key=None):
        """Get the value of child named 'name', and decrypt
        it with 'key' before returning it.
        The default key will be used if the given key is None.
        """ 

        if (key == None):
            key = self.DEFAULT_KEY

        if (len(key) != 16):
             sys.exit("Invalid key, key length sholud be 16")

        value = self.child_get_string(name)
        plaintext = self.RC4(key,pack('H*',value))
        return plaintext



    def toEncodedString(self):
        """Encodes string embedded with special chars like &,<,>.
        This is mainly useful when passing string values embedded
        with special chars like &,<,> to API.

        Example :
        server.invoke("qtree-create","qtree","abc<qt0","volume","vol0")
        """ 
        n = self.element['name']
        s = "<"+n
        keys = self.element['attrkeys']
        vals = self.element['attrvals']
        j = 0

        for i in keys :
            s = s+" "+str(i)+"=\""+str(vals[j])+"\""
            j = j+1

        s = s+">"
        children = self.element['children']

        for i in children :
            c = i
                      
            if (not re.search("NaElement.NaElement",str(c.__class__),re.I)):
                sys.exit("Unexpected reference found, expected NaElement.NaElement not "+ str(c.__class__)+"\n")

            s = s+c.toEncodedString()

        cont = str(self.element['content'])
        cont = NaElement.escapeHTML(cont)
        s = s+cont
        s = s+"</"+n+">"
        return s



#------------------------------------------------------------#
#
# routines beyond this point are "private"
#
#------------------------------------------------------------#

    @staticmethod 
    
    def escapeHTML(cont):
        """ This is a private function, not to be called externally.
        This method converts reserved HTML characters to corresponding entity names.
        """

        cont = re.sub(r'&','&amp;',cont,count=0)
        cont = re.sub(r'<','&lt;',cont,count=0)
        cont = re.sub(r'>','&gt;',cont,count=0)
        cont = re.sub(r"'",'&apos;',cont,count=0)
        cont = re.sub(r'"','&quot;',cont,count=0)

        """ The existence of '&' (ampersand) sign in entity names implies that multiple calls
	to this function will result in non-idempotent encoding. So, to handle such situation
	or when the input itself contains entity names, we reconvert such recurrences to
	appropriate characters.
        """
        cont = re.sub(r'&amp;amp;','&amp;',cont,count=0)
        cont = re.sub(r'&amp;lt;','&lt;',cont,count=0)
        cont = re.sub(r'&amp;gt;','&gt;',cont,count=0)
        cont = re.sub(r'&amp;apos;','&apos;',cont,count=0)
        cont = re.sub(r'&amp;quot;','&quot;',cont,count=0)
        return cont

    def RC4(self, key, value):
        """This is a private function, not to be called from outside NaElement.
        """ 

        box = self.prepare_key(key)
        x,y = 0,0
        plaintext = value
        num = len(plaintext)/self.MAX_CHUNK_SIZE

        integer = int(num)

        if(integer == num):
            num_pieces = integer

        else :
            num_pieces = integer+1

        for piece in range(0,num_pieces-1):
            plaintext = unpack("C*",plaintext[piece * self.MAX_CHUNK_SIZE:(piece*self.MAX_CHUNK_SIZE)+self.MAX_CHUNK_SIZE])

            for i in plaintext:

                if ((x+1) > 255 ):
                    x = 0

                y = y+box[x]

                if(y > 255):
                    y = -256

                box[x],box[y] = box[y],box[x]
                plain_text.append(chr(ord(char) ^ box[(box[x] + box[y]) % 256]))

        return plain_text



    def prepare_key(self, key):
        """This is a private function, not to be called from outside NaElement.
        """ 

        k = unpack('C*',key)
        box = range(255)
        y = 0

        for x in range(255):
            y = (k[x % k]+ box[x] + y) % 256
            box[x],box[y] = box[y],box[x]

        return box



    def attr_set(self, key, value):
        """This is a private function, not to be called from outside NaElement.
        """ 

        arr = self.element['attrkeys']
        arr.append(key)
        self.element['attrkeys'] = arr
        arr = self.element['attrvals']
        arr.append(value)
        self.element['attrvals'] = arr



    def attr_get(self, key):
        """This is a private function, not to be called from outside NaElement.
        """ 

        keys = self.element['attrkeys']
        vals = self.element['attrvals']
        j = 0

        for i in keys:
            if(i == key):
                return vals[j]

            j = j+1

        return None
