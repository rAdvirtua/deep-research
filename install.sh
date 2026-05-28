INSTALL_DIR="$HOME/.deepresearch"
echo "--- Setting up DeepResearch Pipeline in $INSTALL_DIR ---"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
python3 -m venv venv

source venv/bin/activate
pip install --upgrade pip
pip install agno rich requests psutil langchain-groq langchain-google-genai langchain-anthropic langchain-ollama langgraph locvec

echo "#!/bin/bash" > /usr/local/bin/deep-research
echo "cd $INSTALL_DIR && ./venv/bin/python $(pwd)/orchestrator.py \"\$@\"" >> /usr/local/bin/deep-research
chmod +x /usr/local/bin/deep-research

echo "--- Setup complete! Just run 'deep-research' anywhere. ---"
