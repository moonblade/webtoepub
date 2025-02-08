# Web To Epub

I was reading a webseries on kindle by converting it into epub using webtoepub extension. Now that I've caught up with the latest chapter, I'd need to goto the website manually each time a chapter releases, convert it into epub and then upload it to kindle. This is way too much work.

So what this script does is, it takes the RSS feed of the webseries, checks the latest available chapters, checks it against a local db to see if anythings new and if it is, it converts the page into an epub with percollate, and then sends it to kindle with mutt. It shows up in kindle through the kindle email. 

# Screenshot

Kindle screen after running the script

<img width="593" alt="image" src="https://user-images.githubusercontent.com/9362269/232269180-67b13efa-d80c-428d-93c4-6cba9575b0f4.png">


## Update - Feb 2025

Since I now have a homelab k8s setup. I'm updating this to be an image so that it can be run on it instead of the old rpi server.
