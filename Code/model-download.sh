#!/bin/bash

# Start Ollama in the background.
ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

echo "🔴 Retrieve LLAMA3 model..."
ollama pull llama3.2
echo "🟢 Done!"

#echo "🔴 Retrieve Deepseek model..."
#ollama pull deepseek-r1:7b
#echo "🟢 Done!"

#pull command template
#ollama pull llama3.2

# Wait for Ollama process to finish.
#wait $pid

set -x  # turns on shell debugging
echo "Reached end of script"
exit 0  # force a clean exit