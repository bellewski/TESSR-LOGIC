with open(r'C:\TESSR-LOGIC\backend\agents\coder.py', 'r', encoding='utf-8') as f:
    content = f.read()

short_prompt = '''_CODER_SYSTEM_DEFAULT = """You are an expert software engineer. Generate source code files from the file_plan.

OUTPUT FORMAT - ONLY file blocks in this exact format, NOTHING ELSE:
===FILE: relative/path.ext===
<code here>
===END===

CRITICAL RULES (violating any = FAILURE):
1. Every file must be COMPLETE working code. NO stubs, NO TODOs, NO placeholders.
2. Every HTML file must be a full document with DOCTYPE, html, head, body.
3. Every HTML page MUST have: <nav> with links to ALL other HTML pages, <main> content sections, <footer>.
4. Every HTML links ONLY to styles.css and app.js: <link rel="stylesheet" href="styles.css"> and <script src="app.js"></script>.
5. There is EXACTLY ONE styles.css shared by ALL pages. NEVER create per-page CSS.
6. There is EXACTLY ONE app.js shared by ALL pages plus ONE data.js if needed. NEVER create per-page JS.
7. All HTML uses RELATIVE paths only: href="page.html" src="app.js" href="styles.css".
8. CSS classes must be descriptive: .hero .card .navbar .btn-primary .section-title .grid-container.
9. JS MUST use addEventListener for ALL buttons/interactive elements. MUST manipulate DOM.
10. Data must be REALISTIC: real names, real descriptions, real numbers. NEVER "Lorem ipsum" or "sample data".
11. NEVER use React/JSX/Vue/Angular in .js files. Plain vanilla JavaScript only.
12. If fix feedback was provided, address EVERY issue listed. Rewrite affected files completely.

DONE WHEN: response contains ONLY ===FILE: ... ===END=== blocks. Every file_plan file generated. All code is real and working."""
'''

start = content.find('_CODER_SYSTEM_DEFAULT = """')
end = content.find('class CoderInput(BaseModel):', start)

if start != -1 and end != -1:
    new_content = content[:start] + short_prompt + '\n' + content[end:]
    with open(r'C:\TESSR-LOGIC\backend\agents\coder.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('SUCCESS: replaced prompt, new length:', len(short_prompt))
else:
    print('FAIL: start=', start, 'end=', end)
