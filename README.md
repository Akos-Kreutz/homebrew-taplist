# Homebrew Taplist

## Description
I created this application to have a nice looking taplist at home for my guests. As this is only intended for usage on a home network there is no real security to speak of. There is also no admin page, so the configuration is entirely done by modifying the `drinks.json` file and uploading images.

## Usage
I would recommend using the already published [docker image](https://hub.docker.com/repository/docker/kreutzakos/homebrew-taplist). When running this image, the only thing to ensure is that the mount folder is mounted so the custom images and json file can be read by the application. This also allows updating the taplist without any need to restart or rebuild the image.

```
docker run -p 80:80 --rm -v [PATH_TO_MOUNT_FOLDER]:/app/mount kreutzakos/taplist:latest
```

## Example
### Desktop

<p align="left">
  <img title="Desktop" alt='Desktop' src='example/desktop.png' width="1920px" height="1080px"></img>
</p>

### Mobile

<p align="left">
  <img title="Mobile" alt='Mobile' src='example/mobile.png' width="152px" height="1080px"></img>
</p>
