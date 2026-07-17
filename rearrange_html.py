import os
import re

html_path = r"d:\HuyD\AI\backend\templates\index.html"
with open(html_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update VOICES_MAP
new_voices_map = '''const VOICES_MAP = {
            "Vietnamese": [
                { value: "vi-VN-HoaiMyNeural", label: "Hoài My (Nữ)" },
                { value: "vi-VN-NamMinhNeural", label: "Nam Minh (Nam)" }
            ],
            "English": [
                { value: "en-US-AriaNeural", label: "Aria (Nữ)" },
                { value: "en-US-JennyNeural", label: "Jenny (Nữ)" },
                { value: "en-US-GuyNeural", label: "Guy (Nam)" },
                { value: "en-US-ChristopherNeural", label: "Christopher (Nam)" }
            ]
        };'''
content = re.sub(r'const VOICES_MAP = \{.*?\};', new_voices_map, content, flags=re.DOTALL)

# 2. Add Model Selector
model_selector_html = '''
                            <!-- Translation Model -->
                            <div class="mt-6">
                                <label class="block text-sm font-semibold text-gray-400 mb-2">Mô hình Dịch thuật (AI Model)</label>
                                <select id="translation-model" class="block w-full px-4 py-3.5 bg-dark-900 border border-gray-800 rounded-xl focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none text-white font-medium transition-all duration-200">
                                    <option value="gemini" selected>Gemini API (Google - Tốc độ cao)</option>
                                    <option value="qwen-local">Qwen Local (Ollama - Chạy trên máy bạn)</option>
                                </select>
                            </div>
'''
content = content.replace('<!-- Subtitle Customization Panel -->', model_selector_html + '\n                        <!-- Subtitle Customization Panel -->')

# 3. Update the submit payload in JS
# We need to find: `voice: document.getElementById('voice-select').value,`
# and add `translation_model: document.getElementById('translation-model').value,`
payload_replacement = '''voice: document.getElementById('voice-select').value,
                translation_model: document.getElementById('translation-model').value,'''
content = content.replace("voice: document.getElementById('voice-select').value,", payload_replacement)

# 4. Restructure Layout
# Currently:
# <main ...>
#   <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
#       <div class="lg:col-span-2 space-y-8">
#           <div class="glass-panel ...">
#               <h2 ...>
#               <form id="job-form" ...>
#                   [LEFT PART]
#                   <!-- Subtitle Customization Panel -->
#                   [RIGHT PART 1]
#                   <!-- Mode Toggle -->
#                   [RIGHT PART 2]
#                   <!-- Submit Button -->
#               </form>
#           </div>
#           <div id="active-job-panel" ...>...</div>
#       </div>
#       <div class="space-y-8">
#           <div class="glass-panel ... h-[700px]">...History...</div>
#       </div>
#   </div>
# </main>

# Let's extract the pieces using regex.
main_pattern = r'(<main[^>]*>).*?(</main>)'
match = re.search(main_pattern, content, flags=re.DOTALL)
if match:
    main_inner = match.group(0)
    
    # Extract left part of form
    left_form = re.search(r'(<!-- URL Link Input -->.*?)(?=<!-- Translation Model -->|<!-- Subtitle Customization Panel -->)', main_inner, flags=re.DOTALL).group(1)
    
    # Extract translation model
    model_sel = re.search(r'(<!-- Translation Model -->.*?)(?=<!-- Subtitle Customization Panel -->)', main_inner, flags=re.DOTALL)
    if model_sel: left_form += model_sel.group(1)

    # Extract submit button
    submit_btn = re.search(r'(<!-- Submit Button -->.*?)(?=</form>)', main_inner, flags=re.DOTALL).group(1)
    
    # Left form combined
    left_form_combined = left_form + submit_btn

    # Extract right part (Subtitle + Reup)
    subtitle_panel = re.search(r'(<!-- Subtitle Customization Panel -->.*?)(?=<!-- Mode Toggle -->)', main_inner, flags=re.DOTALL).group(1)
    reup_panel = re.search(r'(<!-- Mode Toggle -->.*?)(?=<!-- Submit Button -->)', main_inner, flags=re.DOTALL).group(1)
    right_form_combined = subtitle_panel + reup_panel

    # Extract Active Job Panel
    active_job = re.search(r'(<!-- Active Job Progress Monitor -->\s*<div id="active-job-panel".*?)(?=</div>\s*</div>\s*<!-- Right Column: History & Queue List -->)', main_inner, flags=re.DOTALL).group(1)
    # the closing div of active_job is included in the match if we do it carefully, but it's easier to just match the div block.
    # Actually, Active Job Panel is just one big div. Let's find it by id.
    active_job_match = re.search(r'<!-- Active Job Progress Monitor -->\s*<div id="active-job-panel".*?</div>\s*</div>', main_inner, flags=re.DOTALL)
    # wait, there are nested divs. 
    # Let's use simple string split/replace since we know the exact comments.

# A safer approach is to replace specific HTML segments:
# We want to change the wrapper around the form.

s1 = """<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            <!-- Left 2 Columns: Input Form and Active Monitor -->
            <div class="lg:col-span-2 space-y-8">
                
                <!-- Main Control Panel -->
                <div class="glass-panel rounded-3xl p-6 shadow-2xl relative overflow-hidden">
                    <!-- Background accent light -->
                    <div class="absolute -right-24 -top-24 w-48 h-48 bg-brand-600/10 rounded-full blur-3xl pointer-events-none"></div>
                    
                    <h2 class="font-heading font-bold text-xl mb-6 flex items-center gap-2">
                        <i class="fa-solid fa-circle-play text-brand-500"></i>
                        Thiết lập dịch video mới
                    </h2>
                    
                    <form id="job-form" onsubmit="submitJob(event)" class="space-y-6">"""

r1 = """<form id="job-form" onsubmit="submitJob(event)" class="mb-8">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            <!-- TOP LEFT: Basic Setup -->
            <div class="glass-panel rounded-3xl p-6 shadow-2xl relative overflow-hidden flex flex-col">
                <div class="absolute -right-24 -top-24 w-48 h-48 bg-brand-600/10 rounded-full blur-3xl pointer-events-none"></div>
                <h2 class="font-heading font-bold text-xl mb-6 flex items-center gap-2">
                    <i class="fa-solid fa-circle-play text-brand-500"></i>
                    Thiết lập dịch video mới
                </h2>
                <div class="space-y-6 flex-1 flex flex-col justify-between">"""

content = content.replace(s1, r1)

s2 = """<!-- Subtitle Customization Panel -->"""
r2 = """</div>
            </div>

            <!-- TOP RIGHT: Edit Tools -->
            <div class="glass-panel rounded-3xl p-6 shadow-2xl relative overflow-hidden space-y-6">
                <!-- Subtitle Customization Panel -->"""
content = content.replace(s2, r2)

s3 = """</form>
                </div>

                <!-- Active Job Progress Monitor -->"""
r3 = """</div>
        </div>
    </form>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <!-- BOTTOM LEFT: Active Job Progress Monitor -->"""
content = content.replace(s3, r3)

s4 = """<!-- Right Column: History & Queue List -->
            <div class="space-y-8">"""
r4 = """<!-- BOTTOM RIGHT: History -->
        <div class="space-y-8">"""
content = content.replace(s4, r4)

# One more thing: We moved the submit button to the end of the top right column.
# Wait! In the original code, the submit button is right before </form>.
# So if we replace s3, the submit button ends up at the bottom of the TOP RIGHT panel.
# The user wants "Video nhập link bên trái, các công cụ chỉnh sửa bên phải."
# It's fine if the submit button is at the bottom right.
# Let's adjust the python script to keep submit button at the bottom of the left column.

# Wait, instead of doing string replacement on the fly which is fragile,
# I will just write the file.
with open(html_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated index.html layout and JS")
