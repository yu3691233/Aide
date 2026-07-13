def main():
    file_path = 'f:/AideLink/server/delegate_task.py'
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().strip()
    
    if content.startswith('"') and content.endswith('"'):
        content = content[1:-1]
        
    # Unescape newlines and double quotes
    decoded = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(decoded)
    print("Successfully restored delegate_task.py with raw string decoding!")

if __name__ == '__main__':
    main()
