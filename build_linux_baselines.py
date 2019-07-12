import getopt
import glob
import json
import sys
import sh
import os
import packer
import requests
import fnmatch
from tqdm import tqdm
from lib import packerMod
from lib import serverHelper


def build_base(packer_var_file, common_vars, replace_existing, vmServer=None, prependString = ""):
    TEMP_DIR="tmp"

    vm_name = packer_var_file.strip(".json")

    temp_path = os.path.join("..", "..", TEMP_DIR, prependString + vm_name)

    if not os.path.exists(temp_path):
        os.makedirs(temp_path)

    output = vm_name + "_vmware.box"

    only = ['vmware-iso']

    with open(os.path.join("", packer_var_file)) as packer_var_source:
        packer_vars = json.load(packer_var_source)

    packer_vars.update({
        "vm_name": prependString + vm_name,
        "output": os.path.join("..", "..", "box", output)
    })
    
    packerfile = "./ubuntu.json"
    packer_vars.update(common_vars)

    packer_obj = packerMod(packerfile)
    packer_obj.update_linux_config(packer_vars)

    request = requests.head(packer_vars['iso_url'])
    if request.status_code != 200:
        packer_obj.update_url(packer_vars)

    if vmServer.get_esxi() is not None:
        packer_vars.update(vmServer.get_config())
        packer_obj.use_esxi_config()
    else:
        packer_obj.update_config({
                        "output": "./../../box/" + output
                    })

    packerfile = os.path.join(temp_path, "current_packer.json")
    packer_obj.save_config(packerfile)

    out_file = os.path.join(temp_path, "output.log")
    err_file = os.path.join(temp_path, "error.log")

    p = packer.Packer(str(packerfile), only=only, vars=packer_vars,
                      out_iter=out_file, err_iter=err_file)

    vm = vmServer.get_vm(prependString + vm_name)
    if vm is not None:
        if replace_existing:
            vm.powerOff
            vm.waitForTask(vm.vmObject.Destroy_Task())
        else:
            return p  # just return without exec since ret value is not checked anyways

    try:
        p.build(parallel=True, debug=False, force=False)
    except sh.ErrorReturnCode:
        print "Error: build of " + prependString + vm_name + " returned non-zero"
        return p

    if vmServer.get_esxi() is not None:
        vm = vmServer.get_vm(prependString + vm_name)
        if vm is not None:
            vm.takeSnapshot(snapshotName='baseline')

    return p


def main(argv):

    prependString = ""
    replace_vms = False
    esxi_file = "esxi_config.json"

    try:
        opts, args = getopt.getopt(argv[1:], "c:hp:r", ["prependString="])
    except getopt.GetoptError:
        print argv[0] + ' -n <numProcessors>'
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print argv[0] + " [options]"
            print '-c <file>, --esxiConfig=<file>   use alternate hypervisor config file'
            print '-p <string>, --prependString=<file>   prepend string to the beginning of VM names'
            print '-r, --replace                     replace existing msf_host'
            sys.exit()
        elif opt in ("-c", "--esxiConfig"):
            esxi_file = arg
        elif opt in ("-p", "--prependString"):
            prependString = arg
        elif opt in ("-r", "--replace"):
            replace_vms = True

    vm_server = serverHelper(esxi_file)

    common_var_file = "ubuntu_common.json" # this file will likely be changed to linux_common.json later on
    with open(os.path.join("", common_var_file)) as common_var_source:
        common_vars = json.load(common_var_source)

    os.chdir("boxcutter/ubuntu")

    targets = glob.glob("ubuntu1[468]04.json")
    for target in tqdm(targets):
        build_base(target, common_vars, replace_existing=replace_vms, vmServer=vm_server, prependString=prependString)

    return True

if __name__ == "__main__":
    main(sys.argv)