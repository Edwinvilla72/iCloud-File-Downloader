# iCloud File Downloading Tool

This is a simple application that allows users to log into iCloud and download their photos, videos and files before opting to buy more iCloud storage (like I've had to for so long). 

## User Guide
Upon opening the file, users are prompted to log into their iCloud account. This is securely sent to apple and you will receive a verification code on your Apple device to confirm your login attempt. Upon logging in, you are presented with the option to download to a directory/drive of your choice (I recommend a harddrive or flashdrive, but do you)! 

### Options
#### Photos & Videos (not one or the other right now)
- Organized into folders by month/year as they are downloaded for your convenience :) 
#### iCloud Drive files
- **NOTE**: You have the option to delete photos/videos and iCloud Drive items automatically when they are finished downloading. Though I have seen consistent success with personal testing, **_DO THIS AT YOUR OWN RISK_**! I suggest disabling this option and downloading first, verifying, then deleting manually.

#### iMessages (ONLY ON MacOS)
- Reads conversations downloaded to this Mac from `~/Library/Messages/chat.db`; iCloud login is not required for this tab.
- Click **Load Chats**, select a conversation, then **Open**. The viewer loads the latest 100 messages; **Load More** adds older messages above them. Load Chats refreshes the database snapshot.
- Database reads, thumbnail preparation, and exports run in the background. Rendering happens in small batches, and a status line shows progress. Wait for the current operation before starting another.
- If access is denied, enable **System Settings → Privacy & Security → Full Disk Access** for the app launching the tool (Terminal, your IDE, or the packaged app), then quit and relaunch that app.
- Choose a download folder in the Login tab before exporting. **Export Chat** saves a CSV and locally available attachments. Files not downloaded to this Mac cannot be exported; HEIC images appear as attachment links.
- Install dependencies from `requirements.txt` for support for modern `attributedBody` message text. Unsupported message bodies are marked explicitly rather than silently exported as blank.

I felt bad for making people wait like 2 years for this so I'm doing my best to make the installation approachable while having a few more features in there. 

Hope this helps! Let me know if you have any suggestions, and follow 
