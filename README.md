# Quizzr

This is a hackathon project by the Syntax Syndicate

to use it, simply clone the repo 
mkdir project
cd project
git clone https://github.com/APK-hanal/Quizzr

then create a .env file with 

GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY= Your API key

and run with
cd quizzr
uvicorn backend.main:app --port 8000 (if port 8000 doesnt work, try port 3000)