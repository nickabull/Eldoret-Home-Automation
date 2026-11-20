# Bulldog SD-card Recovery Kit v1

**Status: source committed; not yet exercised on a newly flashed Pi.** No changes have been made to the currently running Bulldog service.

## Recoverability means two things

1. **A reusable installer**, already in this folder.
2. **An actual private backup stored OFF the Pi**. Until you have run the backup tool, copied its archive to encrypted storage on your Mac, and verified that copy, an SD-card failure could still lose your current Hue, Home Connect, SNMP and other secrets/state.

This kit is designed for a clean Raspberry Pi OS Desktop image on a Pi 3 or Pi 5. The old root-level `install-pi.sh` targets a different layout and should **not** be used for Bulldog recovery.

## Prepare the safety net now, while Bulldog works

Download these files together from GitHub's `recovery/` directory:

- `backup-restore.py`
- `install-eldoret.sh`

On the **currently working Bulldog**, open Terminal in that folder and run:

```sh
python3 backup-restore.py backup --output "$HOME/bulldog-private-$(date +%Y%m%d).tar.gz"
```

The archive will contain:

- the Hue / Sky environment file at `~/.config/eldoret.env`
- private SNMP configuration, Home Connect credentials/tokens, device registry, application history and other regular files stored under `~/eldoret-connector/`
- an embedded SHA-256 manifest for every saved file

The source files `connector.py` and `manager.py` are deliberately excluded because they come from GitHub. Files outside the above paths (including Raspberry Pi Connect authentication, display boot configuration, OS accounts, browser profiles, any `/etc/eldoret.env`, and private data stored elsewhere) **are not backed up**. Check for such additional settings and back them up separately if applicable.

**Private archive is not encrypted by this tool.** Copy it directly to a FileVault-protected Mac drive or encrypted external volume, then verify the **copied** archive:

```sh
python3 backup-restore.py verify --archive "/path/on/Mac/to/copied-archive.tar.gz"
```

Never paste this archive, its tokens, or the Hue/SNMP keys into ChatGPT, GitHub, email or an unencrypted cloud drive.

An older archive made on **19 Nov 2026** is useful as a separate historical fallback, but is not the new `bulldog-private-v1` archive format. Create a fresh new-format private backup before considering the disaster-recovery kit ready.

## After an SD card fails / replacing the Pi

1. Use Raspberry Pi Imager on Mac to flash a compatible Raspberry Pi OS Desktop image onto a fresh SD or SSD. Configure normal user, hostname, network and SSH.
2. Start the replacement Pi. Copy this `recovery/` folder plus the **verified** private archive onto its local storage (e.g. in `~/Bulldog-Recovery/`).
3. Copy the contents of this `recovery/` folder into `~/Bulldog-Recovery/` on the newly flashed Pi. Double-click `Install Eldoret.desktop` and approve the desktop's **Trust and Launch** prompt if shown. If that launcher is unavailable on your Pi OS version, run `bash ~/Bulldog-Recovery/install-eldoret.sh` in Terminal (or choose **Execute in Terminal** for the `.sh` file).
4. When asked, paste the **full path** to the private archive (e.g. `/home/username/Downloads/bulldog-private-20261120.tar.gz`). The installer verifies all files before touching services.
5. Type `INSTALL` to proceed. It installs Python/Net-SNMP dependencies, restores private files, downloads `manager.py` and `connector.py` (or uses same-folder copies), creates a user-owned systemd service and checks local HTTP.
6. Open `http://NEW-PI-IP:8765/` and verify Hue, Sky remote, DrayTek WAN2, four UniFi APs, Home Connect, Sky artwork, PS5 and LG discovery. Reconfigure kiosk/browser, display rotation and DSI drivers as needed.
7. **Only then** change the router's IP reservation to replace the previous Bulldog. Keep the previous SD card untouched if it still works.

## Design and safety constraints

- The installer **refuses** to replace an active service or overwrite an existing Eldoret installation.
- It will **not** format a disk, erase the old SD card, change the router, send commands to TVs or Hue, or configure your touchscreen.
- It cannot recover data that was never backed up. Repeat the private backup regularly, especially following new device pairings, token refreshes and integration changes.
- Keep source files alongside the kit for an optional offline recovery. Otherwise initial setup needs internet to download files and packages. All fetched source comes from the existing public main branch; production hardening should add pinned, verified release artifacts.
- The current Mac remains the independently working playout machine.
- **Not yet field-tested on a spare Pi.** The scripts are a first recovery package, not a certified one-click restore. Do not intentionally reflash the functioning Bulldog as a test.

## Backups of the backups

Maintain one encrypted Mac copy and a second independently encrypted storage copy. Record their locations privately. Periodically perform a verification check and, if possible, a rehearsal on a spare Pi.

## Next improvements

Add an optional GUI wrapper for the Terminal installer, verify actual secret-file coverage on Bulldog, capture kiosk/display config in a separate OS-specific profile, make a signed version-pinned offline release ZIP and validate on a freshly flashed Pi 5.
