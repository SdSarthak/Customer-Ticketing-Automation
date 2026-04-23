# Instructions — Convert Report to Word Document

**File to convert:** `AI_Customer_Support_Agent_Report.md`
**Goal:** Produce a submission-ready `.docx` / `.pdf`

---

## Method 1 — Pandoc (Recommended, Best Quality)

**Install Pandoc once:** https://pandoc.org/installing.html

Open a terminal in the project folder (`e:\Ashu_Main\major2\`) and run:

```
pandoc AI_Customer_Support_Agent_Report.md -o AI_Customer_Support_Agent_Report.docx --toc --toc-depth=3
```

Output: `AI_Customer_Support_Agent_Report.docx` in the same folder.

For PDF directly:
```
pandoc AI_Customer_Support_Agent_Report.md -o AI_Customer_Support_Agent_Report.pdf --toc
```

---

## Method 2 — VS Code Extension (No Install Needed if VS Code is used)

1. Open VS Code
2. Install extension: **"Markdown PDF"** by yzane
3. Open `AI_Customer_Support_Agent_Report.md`
4. Press `Ctrl+Shift+P` → type "Markdown PDF: Export (docx)" or "(pdf)"
5. Wait — output appears in the same folder

---

## Method 3 — Online Converter (Zero Install)

1. Go to **https://cloudconvert.com/md-to-docx**
2. Upload `AI_Customer_Support_Agent_Report.md`
3. Click **Convert**
4. Download the `.docx`

Or: **https://word2md.com** works in reverse; for MD→DOCX use cloudconvert or pandoc.

---

## Method 4 — MS Word Directly (Simplest)

1. Open `AI_Customer_Support_Agent_Report.md` in a text editor
2. Copy all content
3. Open MS Word → paste
4. Word will render basic formatting; you'll need to fix headings and tables manually

This is the least accurate method — use only if others fail.

---

## After Conversion — Format in Word

The converted file needs polish before submission:

1. **Font:** Times New Roman, 12pt body
2. **Line spacing:** 1.5
3. **Margins:** 1 inch all sides
4. **Page numbers:** Roman (i, ii, iii) for preliminary pages, Arabic (1, 2, 3) from Chapter 1
5. **Page breaks:** insert before each chapter (`Ctrl+Enter`)
6. **Table of Contents:** References tab → Table of Contents → Update Field (if not already auto-added by pandoc)
7. **Title page:** add institute logo (AITR), center-align
8. **Signatures:** leave space on Certificate, Declaration, Approval Form pages

---

## Note About Diagrams

The report references diagrams like `![Fig. 3.1](diagrams/architecture_diagram.png)` but the PNG files don't exist yet — only the source `.puml` / mermaid files are in the `diagrams/` folder.

**Two options:**

- **Quick:** ignore diagrams for now, convert text-only. Broken image icons will appear; remove them or replace with placeholder text.
- **Full:** render diagrams first (see `diagrams/RENDER_INSTRUCTIONS.md`), then convert. This gives a complete document with figures embedded.

For a minimum viable submission, Method 1 (pandoc) + basic Word formatting is enough.

---

## Final Output

- `AI_Customer_Support_Agent_Report.docx` — editable Word file
- Export to PDF from Word: `File → Export → Create PDF/XPS`
- Print 3 hard copies for department submission

---

## If Pandoc Fails

Common fixes:
- **"pandoc not found":** restart terminal after install, or use full path
- **Tables broken:** pandoc pipe tables occasionally misformat — fix manually in Word
- **Images missing:** ensure PNGs exist at the paths referenced in the MD file

Contact me if any step blocks you.
