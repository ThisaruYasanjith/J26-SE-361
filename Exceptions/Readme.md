cd Exceptions

.venv\Scripts\Activate.ps1

python serve.py


cd "VS Code"

npm run compile

code --extensionDevelopmentPath="$PWD"
