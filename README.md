# UCB-steam

!(https://img.shields.io/github/license/polycornegames/UCB-steam)
!(https://img.shields.io/badge/Build-Unity-blue) !(https://img.shields.io/badge/AWS-EC2-orange) !(https://img.shields.io/badge/AWS-Lambda-orange) !(https://img.shields.io/badge/AWS-SES-orange) !(https://img.shields.io/badge/AWS-S3-orange) !(https://img.shields.io/badge/Build-Steam-lightgrey)

How much time do you spend each week testing your game ? How many time you try to build (maybe fail), package the whole thing with the Steamworks tool, wait for the upload then activate the branch on the Steamworks website ?

Pretty annoying right ?
We did have the same process and because we’re a team of 5, it was challenging to manage the different builds (develop, beta, prod) with always the same build settings.
To avoid this, we wanted to fully automate the build process from Git update to Steam build availability. It is in place now for more than a month and we wanted to share this work with you.
 
In order to have this full automated continuous integration process working, you will need:
- a Bitbucket repository
- a Unity Cloud Build licence (through Unity Plus or higher licence or a Unity Teams licence)
- an Amazon (AWS) enabled account
- a Steamworks account with an existing app

This process is totally hardware free. Everything is executed on the cloud(s) so you don’t have to care about resource availability and network connection stability.
