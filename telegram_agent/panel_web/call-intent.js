'use strict';
window.AgentCallIntent={
  effective(message,mode){
    if(mode!=='relay'||typeof message!=='string')return mode;
    let text=message.toLowerCase().replace(/[‘’ʻʼ]/g,"'");
    if(/javob\s+kutma|faqat\s+(?:ayt|xabar|yetkaz)|just\s+(?:say|relay)|no answer needed|don't wait|только передай|ответ не нужен/.test(text))return mode;
    text=text.replace(/https?:\/\/\S+/g,'').trim();
    const statement=/\b(?:bilmayman|bilaman|aytaman|tushuntiraman|kelaman|kutaman|eslataman|aytamiz|bilamiz)[.!]*$/.test(text);
    const question=text.endsWith('?')||/\bso'ra(?:ng|sin|b)?\b/.test(text)||(!statement&&/\b(?:nima|nimani|nimalar|qayer\w*|qachon|qanday|nega|nechta|qancha|kim)\b/.test(text))||/\b\w{3,}(?:ding|gan|yapti|san|siz|ay|di|ar|shi|ing)mi\b/.test(text)||/^(?:what|where|when|who|why|how|can you|do you|did you|will you|are you|is it)\b/.test(text)||/^(?:что|где|когда|почему|как)(?:\s|$)/.test(text);
    return question?'ask':mode;
  },
  normalize(form){
    const field=form.elements.namedItem('mode'),message=form.elements.namedItem('message').value;
    const mode=this.effective(message,field.value);
    if(mode!==field.value){field.value=mode;field.onchange?.();const note=form.querySelector('#call-intent-note');if(note)note.textContent='Savol aniqlandi: agent javobini ham tinglaydi va sizga natijani yuboradi.';}
    return mode;
  }
};
