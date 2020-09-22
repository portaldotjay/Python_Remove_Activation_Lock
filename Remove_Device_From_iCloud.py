import sys
import subprocess
import pkg_resources
import pyicloud
from pyicloud import PyiCloudService
from pyicloud.exceptions import (
    PyiCloudException,
    PyiCloudFailedLoginException,
    PyiCloudNoDevicesException,
    PyiCloudServiceNotActivatedException,
)
import requests
import json
import getpass
import click

print('Please Login to iCloud.')
username = input('iCloud Username:')
password = getpass.getpass('iCloud Password:')

try: 
    api = PyiCloudService(username, password)
except PyiCloudFailedLoginException as error:
    print("Error logging into iCloud service:", error)
    exit()
else:
    print(('Successfully logged in to ')+api.data['dsInfo']['fullName']+'\'s iCloud account.')
if api.requires_2sa:
    print("Two-factor authentication required. Your trusted devices are:")

    devices = api.trusted_devices
    for i, device in enumerate(devices):
        print(
            "  %s: %s"
            % (i, device.get("deviceName", "SMS to %s") % device.get("phoneNumber"))
        )

    device = click.prompt("Which device would you like to use?", default=0)
    device = devices[device]
    if not api.send_verification_code(device):
        print("Failed to send verification code")
        sys.exit(1)

    code = click.prompt("Please enter validation code")
    if not api.validate_verification_code(device, code):
        print("Failed to verify verification code")
        sys.exit(1)

cookies = api.account.session.cookies
headers = api.account.session.headers
serverContext = api.devices.response['serverContext']
clientContext = {
    "fmly": api.devices.with_family,
    "shouldLocate": True,
    "selectedDevice": "all",
    "deviceListVersion": 1,
}

devices = api.devices.response['content']

url = "https://p66-fmipweb.icloud.com/fmipservice/client/web/remove"
print('Getting devices with activation locks.')
device_dict = {}
for device in devices:
    if device['activationLocked'] == True:
        device_dict[device['id']] = device['name']

print('There are '+str(len(device_dict))+' devices with activation locks on '+api.data['dsInfo']['fullName']+'\'s iCloud account.')
confirm = input('Are you sure you want to remove these devices? (Y)es or (n)o:')
if confirm.lower() != 'y':
    print('Exit')
else:
    print('Removing devices. This may take some time.')    
    for device_id, device_name in device_dict.items():
        payload = {'clientContext':clientContext,'serverContext':serverContext,'device':device_id}
        delete_device = requests.post(
            url,
            headers=headers,
            cookies=cookies,
            params={
                'clientBuildNumber': api.account.params['clientBuildNumber'], 
                'clientMasteringNumber': api.account.params['clientMasteringNumber'], 
                'clientId': api.account.params['clientId'], 
                'dsid': api.account.params['dsid']
                },
            data=json.dumps(payload)
        )
        if delete_device.status_code == 200:
            print('Device '+device_name+' is now unlocked.')
        else:
            print('Device was not deleted. Error code is '+str(delete_device.status_code)+'.')
