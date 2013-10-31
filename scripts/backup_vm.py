import libvirt
import os
import libxml2
import sys
import socket
import tarfile
import lzma
import subprocess
import csv
import shutil


def getXMLData(ctx, path):
    res = ctx.xpathEval(path)
    if res is None or len(res) == 0:
        value = "Unknown"
    else:
        value = res[0].content
        return value


def getVMs():
    conn = libvirt.open("qemu:///system")
    if conn is None:
        print 'Failed to open connection to the hypervisor'
        sys.exit(1)

    dom_u = conn.listDefinedDomains()

    vm_obj = []
    for u in dom_u:
        vm_obj.append(conn.lookupByName(u))
    return vm_obj


def virtConnection():
    conn = libvirt.open("qemu:///system")
    if conn is None:
        print 'Failed to open connection to the hypervisor'
        sys.exit(1)

    dom_u = conn.listDefinedDomains()
    #dom_a = conn.listDomainsID()
    return dom_u


def returnVMObj(vm_obj, vm_host):

    instance_name = []
    data_dir = []
    data_print = []
    for x in vm_obj:

        xmldoc = x.XMLDesc(0)
        tmp_doc = libxml2.parseDoc(xmldoc)
        ctx = tmp_doc.xpathNewContext()
        instance_name.append(getXMLData(ctx, "/domain/name"))
        dict_var = {"host": vm_host,
                    "ec2-id": getXMLData(ctx, "/domain/name"),
                    "uuid": getXMLData(ctx, "/domain/uuid"),
                    "ip": getXMLData(ctx,
                    ("/domain/devices/interface/filterref/" +
                     "parameter[@name='IP']/@value"))
                    }

        data_print.append(dict_var)

        devs = ctx.xpathEval("/domain/devices/*")
        for d in devs:
            ctx.setContextNode(d)
            data_dir.append(getXMLData(ctx, "source/@file"))

    return instance_name, data_dir, data_print


def filterName(vm_obj):
    filter_dir = []
    vm_obj = [x for x in vm_obj if x is not None]
    for i in vm_obj:
        filter_dir.append((os.path.dirname(i)))

    return filter_dir


def getHostName():
    return socket.gethostname()


def makeHostDirectory(root_path, host_name, instance_name):
    path = root_path + host_name + "/" + instance_name
    os.makedirs(path)
    return path


def runExecute(path):
    output = path + "/" + "disk.raw"
    path = path + "/" + "disk"

    conv_raw = subprocess.Popen(['qemu-img',
                                 'convert', '-O', 'raw',
                                path, output], shell=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    return conv_raw.communicate()[0].split()


def listCopy(path, exclude, new_path):
    data_list = os.listdir(path)
    data_list.remove(exclude)
    for x in data_list:
        cur_ = path + "/" + x
        new_ = new_path + "/" + x

        conv_raw = subprocess.Popen(['cp', cur_, new_],
                                    shell=False,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        conv_raw.communicate()[0].split()


def makeTarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir,
                arcname=os.path.basename(source_dir))


def makeLZMATarfle(instance_name, output_dir):
    tar_name = instance_name + ".tar.xz"
    tar_name_dir = output_dir + ".tar.xz"

    xz_file = lzma.LZMAFile(tar_name_dir, mode='w')
    with tarfile.open(mode='w', fileobj=xz_file) as tar_xz_file:
        tar_xz_file.add(output_dir, arcname=tar_name)
    xz_file.close()


def writeToCSV(data_w, hostname, root_path):
    filename = root_path + hostname + ".csv"
    if os.path.exists(filename) is False:
        try:
            record = open(filename, 'w+')
            writer = csv.writer(record, delimiter=',',
                                quoting=csv.QUOTE_ALL)
            writer.writerow(['host', 'uuid', 'ec2-id', 'ip'])
            writer.writerow([data_w.get('host'), data_w.get('uuid'),
                             data_w.get('ec2-id'), data_w.get('ip')])
        except IOError, e:
            print "File Error" % e
            raise SystemExit
    else:
        with open(filename, 'a') as w:
            writer = csv.writer(w, delimiter=',',
                                quoting=csv.QUOTE_ALL)
            writer.writerow([data_w.get('host'), data_w.get('uuid'),
                             data_w.get('ec2-id'), data_w.get('ip')])


def removeFolder(work_path):
    shutil.rmtree(work_path)


prt_data = returnVMObj(getVMs(), getHostName())
root_path = '/var/lib/nova/instances/'

for w in prt_data[2]:
    writeToCSV(w, getHostName(), root_path)

for k in prt_data[0]:
    instance_path = root_path + k

    work_path = makeHostDirectory(root_path, getHostName(), k)
    convert = runExecute(instance_path)

    listCopy(instance_path, 'disk', work_path)
    makeLZMATarfle(k, work_path)
    removeFolder(work_path)
