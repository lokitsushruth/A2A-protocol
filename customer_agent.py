from flask import Flask, request, jsonify
import sqlite3
import json
import uuid
from datetime import datetime
import os

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    GROQ_API_KEY = input("Enter your Groq API key: ")
GROQ_MODEL = "llama3-70b-8192" 


llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name=GROQ_MODEL
)

class CustomerAgent:
    def __init__(self):
        self.conn = sqlite3.connect('customers.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def add_customer(self, name, email=None):
        self.cursor.execute(
            'INSERT INTO customers (name, email) VALUES (?, ?)',
            (name, email)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def list_customers(self):
        self.cursor.execute('SELECT id, name, email, created_at FROM customers')
        return self.cursor.fetchall()

    def delete_customer(self, customer_id):
        self.cursor.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
        self.conn.commit()
        return self.cursor.rowcount  # Number of rows deleted

    def update_customer(self, customer_id, name=None, email=None):
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if not updates:
            return 0  
        params.append(customer_id)
        sql = f'UPDATE customers SET {", ".join(updates)} WHERE id = ?'
        self.cursor.execute(sql, tuple(params))
        self.conn.commit()
        return self.cursor.rowcount  

    def process_command(self, command):
        system_prompt = """
You are an assistant that converts user requests about customers into structured JSON commands.
Supported commands:
- To add a customer: {"intent":"add_customer","parameters":{"name":"customer name","email":"optional email"}}
- To list customers: {"intent":"list_customers","parameters":{}}
- To delete a customer: {"intent":"delete_customer","parameters":{"id": customer_id}}
- To update a customer: {"intent":"update_customer","parameters":{"id": customer_id, "name": "new name (optional)", "email": "new email (optional)"}}
If email or name are not mentioned in update, omit those fields.
Examples:
User: Add Rahul to customers
Output: {"intent":"add_customer","parameters":{"name":"Rahul"}}
User: Add Priya with email priya@example.com
Output: {"intent":"add_customer","parameters":{"name":"Priya","email":"priya@example.com"}}
User: List all customers
Output: {"intent":"list_customers","parameters":{}}
User: Show me all customers
Output: {"intent":"list_customers","parameters":{}}
User: Delete customer ID:1
Output: {"intent":"delete_customer","parameters":{"id":1}}
User: Remove customer 2
Output: {"intent":"delete_customer","parameters":{"id":2}}
User: Update customer 3 name to 'Rahul Sharma'
Output: {"intent":"update_customer","parameters":{"id":3,"name":"Rahul Sharma"}}
User: Update customer 4 email to 'new.email@example.com'
Output: {"intent":"update_customer","parameters":{"id":4,"email":"new.email@example.com"}}
User: Update customer 5 name to 'Arjun Patel' and email to 'arjun@patel.com'
Output: {"intent":"update_customer","parameters":{"id":5,"name":"Arjun Patel","email":"arjun@patel.com"}}
Return only the JSON, no extra text.
"""
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=command)
            ]
            response = llm.invoke(messages)
            result = response.content.strip()

            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                # Try to extract the first {...} block
                import re
                match = re.search(r'\{.*\}', result, re.DOTALL)
                if match:
                    parsed = json.loads(match.group())
                else:
                    raise ValueError("No JSON found in LLM response.")

            intent = parsed.get("intent")
            params = parsed.get("parameters", {})

            if intent == "add_customer":
                name = params.get("name", "").strip()
                if not name:
                    raise ValueError("Customer name missing")
                email = params.get("email", None)
                customer_id = self.add_customer(name, email)
                return {
                    'status': 'success',
                    'action': 'add_customer',
                    'message': f'Customer \"{name}\" added',
                    'customer': {'id': customer_id, 'name': name, 'email': email}
                }

            elif intent == "list_customers":
                customers = self.list_customers()
                formatted_customers = [
                    {
                        'id': c[0],
                        'name': c[1],
                        'email': c[2],
                        'created_at': c[3]
                    } for c in customers
                ]
                return {
                    'status': 'success',
                    'action': 'list_customers',
                    'message': f'Found {len(customers)} customer(s)',
                    'customers': formatted_customers,
                    'count': len(customers)
                }

            elif intent == "delete_customer":
                cust_id = params.get("id")
                if not cust_id:
                    raise ValueError("Customer ID missing")
                deleted = self.delete_customer(cust_id)
                if deleted:
                    return {
                        'status': 'success',
                        'action': 'delete_customer',
                        'message': f'Customer with ID {cust_id} deleted'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'delete_customer',
                        'message': f'No customer found with ID {cust_id}'
                    }

            elif intent == "update_customer":
                cust_id = params.get("id")
                if not cust_id:
                    raise ValueError("Customer ID missing")
                name = params.get("name", None)
                email = params.get("email", None)
                updated = self.update_customer(cust_id, name, email)
                if updated:
                    return {
                        'status': 'success',
                        'action': 'update_customer',
                        'message': f'Customer with ID {cust_id} updated'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'update_customer',
                        'message': f'No customer found with ID {cust_id} or nothing to update'
                    }

            else:
                return {
                    'status': 'error',
                    'action': 'unknown',
                    'message': 'Command not recognized'
                }

        except Exception as e:
            return {
                'status': 'error',
                'action': 'parse_command',
                'message': f'Command failed: {str(e)}'
            }


customer_agent = CustomerAgent()


@app.route('/.well-known/agent.json')
def agent_card():
    return jsonify({
        "name": "CustomerAgent",
        "description": "Manages customer database operations using natural language",
        "version": "1.2.0",
        "url": "http://localhost:5002",
        "capabilities": {
            "streaming": False,
            "function_calls": True,
            "enhanced_responses": True
        },
        "skills": [
            {
                "id": "manage_customers",
                "name": "Customer Management",
                "description": "Add, list, delete, and update customers using natural language",
                "examples": [
                    "Add Rahul to customers",
                    "Add Priya with email priya@example.com",
                    "List all customers",
                    "Show me all customers",
                    "Delete customer ID:1",
                    "Remove customer 2",
                    "Update customer 3 name to 'Rahul Sharma'",
                    "Update customer 4 email to 'new.email@example.com'",
                    "Update customer 5 name to 'Arjun Patel' and email to 'arjun@patel.com'"
                ]
            }
        ],
        "endpoints": {
            "task_send": "http://localhost:5002/task/send"
        }
    })


@app.route('/task/send', methods=['POST'])
def handle_task():
    data = request.get_json()
    command = ""
    if 'message' in data and 'parts' in data['message']:
        for part in data['message']['parts']:
            if part['type'] == 'text':
                command = part['text']
                break

    task_id = data.get('id', str(uuid.uuid4()))

    # Process the command using the agent
    result = customer_agent.process_command(command)

    # Build A2A response
    response = {
        "id": task_id,
        "status": {
            "state": "completed" if result['status'] == 'success' else "failed",
            "timestamp": datetime.now().isoformat()
        },
        "artifacts": [{
            "id": str(uuid.uuid4()),
            "type": "text",
            "parts": [{"type": "text", "text": json.dumps(result)}]
        }]
    }

    return jsonify(response)


if __name__ == '__main__':
    print("🚀 Customer Agent (LangChain+Groq) running on http://localhost:5002")
    app.run(host='localhost', port=5002, debug=True)
