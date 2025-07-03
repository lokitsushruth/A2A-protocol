import requests
import json
import uuid
from datetime import datetime
from openai import OpenAI


class A2ARouter:
    def __init__(self):
        self.agents = {}



        self.discover_agents()

    def discover_agents(self):
        """Discover available agents by fetching their Agent Cards"""
        agent_urls = [
            "http://localhost:5001",
            "http://localhost:5002"
        ]

        for url in agent_urls:
            try:
                response = requests.get(f"{url}/.well-known/agent.json")
                if response.status_code == 200:
                    agent_card = response.json()
                    self.agents[agent_card['name']] = agent_card
                    print(f"✅ Discovered agent: {agent_card['name']} at {url}")
                else:
                    print(f"❌ Failed to discover agent at {url}")
            except Exception as e:
                print(f"❌ Error discovering agent at {url}: {e}")

    def route_command(self, command):
        """Route command to appropriate agent based on keywords"""
        cmd_lower = command.lower()

        if 'product' in cmd_lower:
            return 'ProductAgent'
        elif 'customer' in cmd_lower:
            return 'CustomerAgent'
        else:
            return None



    def extract_result_from_a2a_response(self, a2a_response):
        """Extract the actual result JSON from A2A response structure"""
        try:
            # Navigate through A2A response structure to get the actual result
            artifacts = a2a_response.get('artifacts', [])
            if artifacts:
                parts = artifacts[0].get('parts', [])
                if parts:
                    result_text = parts[0].get('text', '{}')
                    return json.loads(result_text)
            return {}
        except Exception as e:
            print(f"⚠️  Error extracting result: {e}")
            return {}

    def send_task(self, agent_name, command):
        """Send A2A task to specific agent"""
        if agent_name not in self.agents:
            return {'error': f'Agent {agent_name} not found'}

        agent_card = self.agents[agent_name]
        endpoint = agent_card['endpoints']['task_send']

        # A2A task format
        task = {
            "id": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": command
                    }
                ]
            },
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n🚀 SENDING TO {agent_name}")
        print(f"Endpoint: {endpoint}")
        print(f"A2A Task: {json.dumps(task, indent=2)}")

        try:
            response = requests.post(endpoint, json=task)
            if response.status_code == 200:
                a2a_result = response.json()
                print(f"\n✅ RECEIVED FROM {agent_name}")
                print(f"A2A Response: {json.dumps(a2a_result, indent=2)}")

                # Extract the actual result for OpenAI processing
                extracted_result = self.extract_result_from_a2a_response(a2a_result)

                # Get user-friendly summary


                return {
                    'a2a_response': a2a_result,
                    'extracted_result': extracted_result,
                }
            else:
                return {'error': f'HTTP {response.status_code}: {response.text}'}
        except Exception as e:
            return {'error': str(e)}

    def process_command(self, command):
        """Process user command by routing to appropriate agent"""
        agent_name = self.route_command(command)

        if not agent_name:
            return {'error': 'No suitable agent found for command'}

        return self.send_task(agent_name, command)


def main():
    print("🌐 Enhanced A2A Router")

    router = A2ARouter()

    print(f"\n📋 Discovered {len(router.agents)} agents:")
    for name, card in router.agents.items():
        print(f"  - {name}: {card['description']}")

    print("\n💬 Enter commands (or 'quit' to exit):")
    print("Examples:")
    print("  - add iPhone product 999.99")
    print("  - add rahul to customer")
    print("  - list all products")
    print("  - list all customers")

    while True:
        command = input("\n> ").strip()

        if command.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break

        if not command:
            continue

        result = router.process_command(command)

        if 'error' in result:
            print(f"\n❌ Error: {result['error']}")
        else:
            # Display user-friendly response
            if result.get('user_friendly'):

                print(result['user_friendly'])

            # Show the technical details
            print(f"\n📋 Technical Details:")
            print(f"Extracted Result: {json.dumps(result.get('extracted_result', {}), indent=2)}")


if __name__ == '__main__':
    main()
