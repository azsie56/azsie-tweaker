# AZSIE Tweaker Tool

Open-source Windows system tuning tool for users who understand system-level changes.

## Release contents

- The unverified embedded Base64 logo was removed; the app uses the AZSIE text mark.
- No private data is embedded. The Discord URL is public.
- A visible disclaimer warns about system changes.
- Released under GNU GPL v3. See `LICENSE`.

## Important warning

This program changes Windows Registry values, services, and system settings. Use it at your own risk. Create a System Restore Point and back up important data before using it.

Disabling Windows Defender or Windows Update can reduce malware protection and prevent security patches. Do not disable these features unless you understand the risks and have a clear recovery plan.

There is no warranty that this program is suitable for every computer or will operate without damage. Read every confirmation before using high-impact actions.

## Download the Windows EXE

????????????????????? `AZSIE-Tweaker.exe` ??????? GitHub Release ?????? ?????????????? Python ???? dependencies ?????????

Windows SmartScreen ???????????????????????????????????????????????? code-signing ?????????? SHA256 ??? `SHA256SUMS.txt` ???????????? ???????? Run as administrator ??????????????????????????????

## Install and run

Windows and Python 3.10 or newer are required.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python azsie_tweakers.py
```

Some actions require Administrator privileges.

The app uses GitHub only for optional update checks and download statistics. The configured repository is `azsie56/azsie-tweaker`.

## SHA256 checksums for releases

Create checksums for release assets with:

```powershell
.\generate_sha256.ps1 -ReleaseDir .\release-assets
```

This creates `SHA256SUMS.txt`. Verify an asset with:

```powershell
Get-FileHash .\release-assets\<file> -Algorithm SHA256
```

The `.github/workflows/release-sha256.yml` workflow automatically creates and attaches `SHA256SUMS.txt` to published GitHub Releases.

## License

Copyright (c) AZSIE Community. This project is distributed under the GNU General Public License v3.0 only. Anyone distributing the program or a modified version must provide the source code and license terms. See `LICENSE`.
