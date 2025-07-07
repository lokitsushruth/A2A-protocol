from flask import Flask, request, jsonify
import sqlite3
import json
import uuid
from datetime import datetime
import os

from openai import OpenAI

app = Flask(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    OPENAI_API_KEY = input("Enter your OpenAI API key: ")

client = OpenAI(api_key=OPENAI_API_KEY)


class ProductAgent:
    def __init__(self):
        self.conn = sqlite3.connect('products.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def add_product(self, name, description=None):
        self.cursor.execute(
            'INSERT INTO products (name, description) VALUES (?, ?)',
            (name, description)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def list_products(self):
        self.cursor.execute('SELECT id, name, description, created_at FROM products')
        return self.cursor.fetchall()

    def delete_product(self, product_id):
        self.cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
        self.conn.commit()
        return self.cursor.rowcount  # Number of rows deleted

    def update_product(self, product_id, name=None, description=None):
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if not updates:
            return 0  # Nothing to update
        params.append(product_id)
        sql = f'UPDATE products SET {", ".join(updates)} WHERE id = ?'
        self.cursor.execute(sql, tuple(params))
        self.conn.commit()
        return self.cursor.rowcount  # Number of rows updated

    def process_command(self, command):
        system_prompt = """
You are an assistant that converts user requests about products into structured JSON commands.
Supported commands:
- To add a product: {"intent":"add_product","parameters":{"name":"product name","description":"optional description"}}
- To list products: {"intent":"list_products","parameters":{}}
- To delete a product: {"intent":"delete_product","parameters":{"id": product_id}}
- To update a product: {"intent":"update_product","parameters":{"id": product_id, "name": "new name (optional)", "description": "new description (optional)"}}
If description or name are not mentioned in update, omit those fields.
Examples:
User: Add iPhone to products
Output: {"intent":"add_product","parameters":{"name":"iPhone"}}
User: Add a Yoga Mat with description Eco-friendly
Output: {"intent":"add_product","parameters":{"name":"Yoga Mat","description":"Eco-friendly"}}
User: List all products
Output: {"intent":"list_products","parameters":{}}
User: Show me all items
Output: {"intent":"list_products","parameters":{}}
User: Delete product ID:1
Output: {"intent":"delete_product","parameters":{"id":1}}
User: Remove product 2
Output: {"intent":"delete_product","parameters":{"id":2}}
User: Update product 3 name to 'Super Phone'
Output: {"intent":"update_product","parameters":{"id":3,"name":"Super Phone"}}
User: Update product 4 description to 'Limited edition'
Output: {"intent":"update_product","parameters":{"id":4,"description":"Limited edition"}}
User: Update product 5 name to 'Ultra Laptop' and description to '2025 model'
Output: {"intent":"update_product","parameters":{"id":5,"name":"Ultra Laptop","description":"2025 model"}}
Return only the JSON, no extra text.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ],
                temperature=0.1,
                max_tokens=200
            )
            result = response.choices[0].message.content.strip()
            parsed = json.loads(result)
            intent = parsed.get("intent")
            params = parsed.get("parameters", {})

            if intent == "add_product":
                name = params.get("name", "").strip()
                if not name:
                    raise ValueError("Product name missing")
                description = params.get("description", None)
                product_id = self.add_product(name, description)
                return {
                    'status': 'success',
                    'action': 'add_product',
                    'message': f'Product \"{name}\" added',
                    'product': {'id': product_id, 'name': name, 'description': description}
                }

            elif intent == "list_products":
                products = self.list_products()
                formatted_products = [
                    {
                        'id': p[0],
                        'name': p[1],
                        'description': p[2],
                        'created_at': p[3]
                    } for p in products
                ]
                return {
                    'status': 'success',
                    'action': 'list_products',
                    'message': f'Found {len(products)} product(s)',
                    'products': formatted_products,
                    'count': len(products)
                }

            elif intent == "delete_product":
                prod_id = params.get("id")
                if not prod_id:
                    raise ValueError("Product ID missing")
                deleted = self.delete_product(prod_id)
                if deleted:
                    return {
                        'status': 'success',
                        'action': 'delete_product',
                        'message': f'Product with ID {prod_id} deleted'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'delete_product',
                        'message': f'No product found with ID {prod_id}'
                    }

            elif intent == "update_product":
                prod_id = params.get("id")
                if not prod_id:
                    raise ValueError("Product ID missing")
                name = params.get("name", None)
                description = params.get("description", None)
                updated = self.update_product(prod_id, name, description)
                if updated:
                    return {
                        'status': 'success',
                        'action': 'update_product',
                        'message': f'Product with ID {prod_id} updated'
                    }
                else:
                    return {
                        'status': 'error',
                        'action': 'update_product',
                        'message': f'No product found with ID {prod_id} or nothing to update'
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


product_agent = ProductAgent()


@app.route('/.well-known/agent.json')
def agent_card():
    return jsonify({
        "name": "ProductAgent",
        "description": "Manages product database operations using natural language",
        "version": "1.2.0",
        "url": "http://localhost:5001",
        "capabilities": {
            "streaming": False,
            "function_calls": True,
            "enhanced_responses": True
        },
        "skills": [
            {
                "id": "manage_products",
                "name": "Product Management",
                "description": "Add, list, delete, and update products using natural language",
                "examples": [
                    "Add iPhone to products",
                    "Add a Yoga Mat with description Eco-friendly",
                    "List all products",
                    "Show me all items",
                    "Delete product ID:1",
                    "Remove product 2",
                    "Update product 3 name to 'Super Phone'",
                    "Update product 4 description to 'Limited edition'",
                    "Update product 5 name to 'Ultra Laptop' and description to '2025 model'"
                ]
            }
        ],
        "endpoints": {
            "task_send": "http://localhost:5001/task/send"
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

    # Process the command using the agent (now with NL support)
    result = product_agent.process_command(command)

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
    print("🚀 Product Agent (NL) running on http://localhost:5001")
    app.run(host='localhost', port=5001, debug=True)

