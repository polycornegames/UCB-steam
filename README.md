# UCB-steam

![GitHub](https://img.shields.io/badge/licence-CC--BY--NC--ND--4.0-orange)

![GitHub](https://img.shields.io/badge/GIT-Bitbucket-blue) ![GitHub](https://img.shields.io/badge/Build-Unity-blue) ![GitHub](https://img.shields.io/badge/AWS-EC2-orange) ![GitHub](https://img.shields.io/badge/AWS-Lambda-orange) ![GitHub](https://img.shields.io/badge/AWS-SES-orange) ![GitHub](https://img.shields.io/badge/AWS-S3-orange) ![GitHub](https://img.shields.io/badge/AWS-DynamoDB-orange) ![GitHub](https://img.shields.io/badge/AWS-IAM-orange) ![GitHub](https://img.shields.io/badge/Build-Steamworks-black) ![GitHub](https://img.shields.io/badge/Build-ItchIO-ff96b4) ![GitHub](https://img.shields.io/badge/Hook-Discord-5865f2) ![GitHub](https://img.shields.io/badge/Hook-Bitbucket-blue) ![GitHub](https://img.shields.io/badge/Ubuntu-20.4-77216f)

How much time do you spend each week testing your game ? How many time you try to build (maybe fail), package the whole thing with the Steamworks tool, wait for the upload then activate the branch on the Steamworks website ?

Pretty annoying right ?
We did have the same process and because we’re a team of 5, it was challenging to manage the different builds (develop, beta, prod) with always the same build settings.
To avoid this, we wanted to fully automate the build process from Git update to Steam build availability. It is in place now for more than a month and we wanted to share this work with you.
 
In order to have this full automated continuous integration process working, you will need:
- a Bitbucket repository
- a Unity Cloud Build (UCB) licence (through Unity Plus or higher licence or a Unity Teams licence)
- an Amazon (AWS) enabled account
- a Steamworks account with an existing app

This process is totally hardware free. Everything is executed on the cloud(s) so you don’t have to care about resource availability and network connection stability.

![image](https://user-images.githubusercontent.com/81538937/112906498-8d2ab500-90ec-11eb-952a-1daa196f2ab7.png)

# Files included in this repository

- UCB-DeployOnSteam-Handler.py : Python script used for the AWS Lambda function
- UCB-steam-startup-script.example : Bash script that execute the process at the machine startup
- UCB-steam.config.example : Configuration file used by UCB-steam.py
- UCB-steam.py : Python script that download the builds from UCB, create the Steam package then upload them to Steam
