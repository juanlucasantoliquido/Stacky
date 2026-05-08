"""Fix IIS Express applicationhost.config for ADO-119 QA tests."""
import os, re

docs = os.environ.get('USERPROFILE', '') + '\\OneDrive - UBIMIA\\Documentos'
cfg = os.path.join(docs, 'IISExpress\\config\\applicationhost.config')

with open(cfg, 'r', encoding='utf-8') as f:
    content = f.read()

# Find current site config
m = re.search(r'<site name="AgendaWebPacifico".*?</site>', content, re.DOTALL)
if m:
    print("Found AgendaWebPacifico site:")
    print(m.group(0)[:600])
    
    # Replace with clean single-app version
    old_site = m.group(0)
    new_site = '''            <site name="AgendaWebPacifico" id="2">
                <application path="/AgendaWeb" applicationPool="Clr4IntegratedAppPool">
                    <virtualDirectory path="/" physicalPath="N:\\GIT\\RS\\RSPACIFICO\\trunk\\OnLine\\AgendaWeb" />
                </application>
                <bindings>
                    <binding protocol="http" bindingInformation=":35017:localhost" />
                </bindings>
            </site>'''
    
    content = content.replace(old_site, new_site)
    with open(cfg, 'w', encoding='utf-8') as f:
        f.write(content)
    print("\nConfig updated: single /AgendaWeb application only")
else:
    print("Site not found! Checking if it needs to be added...")
    # Check what sites exist
    sites = re.findall(r'<site name="[^"]*"', content)
    print("Existing sites:", sites)
    
    # Add the new site before </sites>
    new_site = '''
            <site name="AgendaWebPacifico" id="2">
                <application path="/AgendaWeb" applicationPool="Clr4IntegratedAppPool">
                    <virtualDirectory path="/" physicalPath="N:\\GIT\\RS\\RSPACIFICO\\trunk\\OnLine\\AgendaWeb" />
                </application>
                <bindings>
                    <binding protocol="http" bindingInformation=":35017:localhost" />
                </bindings>
            </site>
'''
    content = content.replace('</sites>', new_site + '        </sites>')
    with open(cfg, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Site added to applicationhost.config")

print("Done.")
