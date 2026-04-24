# iCloud-File-Downloader
An application that allows users to download all of their files directly from iCloud onto their desired directory. 

--How it works--
First, fill in iCloud information. Before logging in, select a folder you would like your files to download to. Then, download and wait for your files to appear in the selected location.

## Windows release build

This app is packaged as a windowed Windows executable, so it does not open a separate console window.

### Local build

```powershell
./build_release.ps1
```

The build output is:

```text
release-dist/iCloud_aio_tool.exe
```

### GitHub release build

Pushing a tag like `v1.0.0` triggers the GitHub Actions workflow in `.github/workflows/release.yml`, which:

- installs Python and dependencies
- builds `dist/iCloud_aio_tool.exe`
- uploads the executable as both a workflow artifact and a GitHub release asset

--Features to add in the future (hopefully)...---
- Downloading Backups (in any possible way, but directly backing up to file location isn't possible)
- Downloading FILES (from iCloud Drive, not just pictures and videos)
- Is there any way to download iMessages to a location like a harddrive?? (probably not but I'll look into it eventually)
- Same for emails ^
