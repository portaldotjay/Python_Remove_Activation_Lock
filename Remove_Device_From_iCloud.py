import argparse
import getpass
import json
import sys

try:
    import click
except ImportError:  # pragma: no cover - optional dependency for CLI prompts
    click = None

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

try:
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import (
        PyiCloudException,
        PyiCloudFailedLoginException,
        PyiCloudNoDevicesException,
        PyiCloudServiceNotActivatedException,
    )
except ImportError:  # pragma: no cover - library-only import should still work
    PyiCloudService = None
    PyiCloudException = Exception
    PyiCloudFailedLoginException = Exception
    PyiCloudNoDevicesException = Exception
    PyiCloudServiceNotActivatedException = Exception

REMOVE_DEVICE_URL = "https://p66-fmipweb.icloud.com/fmipservice/client/web/remove"


def _require_dependency(name, package):
    if package is None:
        raise RuntimeError(f"{name} is required to use this script.")


def login_to_icloud(username, password):
    _require_dependency("pyicloud", PyiCloudService)
    try:
        return PyiCloudService(username, password)
    except PyiCloudFailedLoginException as error:
        raise RuntimeError(f"Error logging into iCloud service: {error}") from error


def get_trusted_device_choice(api):
    if not api.requires_2sa:
        return None

    if click is None:
        raise RuntimeError("click is required for two-factor authentication prompts.")

    print("Two-factor authentication required. Your trusted devices are:")
    devices = api.trusted_devices
    for index, device in enumerate(devices):
        print(
            "  %s: %s"
            % (index, device.get("deviceName", "SMS to %s") % device.get("phoneNumber"))
        )

    device = click.prompt("Which device would you like to use?", default=0)
    device = devices[device]
    if not api.send_verification_code(device):
        raise RuntimeError("Failed to send verification code")

    code = click.prompt("Please enter validation code")
    if not api.validate_verification_code(device, code):
        raise RuntimeError("Failed to verify validation code")
    return device


def get_activation_locked_devices(api):
    devices = api.devices.response.get("content", [])
    return {
        device["id"]: device.get("name", "Unknown device")
        for device in devices
        if device.get("activationLocked") is True and "id" in device
    }


def build_client_context(api):
    return {
        "fmly": api.devices.with_family,
        "shouldLocate": True,
        "selectedDevice": "all",
        "deviceListVersion": 1,
    }


def remove_devices(api, device_dict):
    _require_dependency("requests", requests)

    cookies = api.account.session.cookies
    headers = api.account.session.headers
    server_context = api.devices.response.get("serverContext", {})
    client_context = build_client_context(api)

    print("Removing devices. This may take some time.")
    for device_id, device_name in device_dict.items():
        payload = {"clientContext": client_context, "serverContext": server_context, "device": device_id}
        delete_device = requests.post(
            REMOVE_DEVICE_URL,
            headers=headers,
            cookies=cookies,
            params={
                "clientBuildNumber": api.account.params["clientBuildNumber"],
                "clientMasteringNumber": api.account.params["clientMasteringNumber"],
                "clientId": api.account.params["clientId"],
                "dsid": api.account.params["dsid"],
            },
            data=json.dumps(payload),
        )
        if delete_device.status_code == 200:
            print("Device " + device_name + " is now unlocked.")
        else:
            print("Device was not deleted. Error code is " + str(delete_device.status_code) + ".")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remove activation-locked devices from an iCloud account.")
    parser.add_argument("--username", help="iCloud username")
    parser.add_argument("--password", help="iCloud password")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args(argv)

    print("Please Login to iCloud.")
    username = args.username or input("iCloud Username:")
    password = args.password or getpass.getpass("iCloud Password:")

    try:
        api = login_to_icloud(username, password)
    except RuntimeError as error:
        print(error)
        return 1

    print(f"Successfully logged in to {api.data['dsInfo']['fullName']}'s iCloud account.")
    try:
        get_trusted_device_choice(api)
    except RuntimeError as error:
        print(error)
        return 1

    device_dict = get_activation_locked_devices(api)
    print(
        "There are "
        + str(len(device_dict))
        + " devices with activation locks on "
        + api.data["dsInfo"]["fullName"]
        + "'s iCloud account."
    )

    if not args.yes:
        confirm = input("Are you sure you want to remove these devices? (Y)es or (n)o:")
        if confirm.lower() != "y":
            print("Exit")
            return 0

    try:
        remove_devices(api, device_dict)
    except RuntimeError as error:
        print(error)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
