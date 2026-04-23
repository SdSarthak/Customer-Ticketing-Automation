# How to Render All Diagrams

## Quick Reference Table

| Diagram | File | Render Tool | Output Format |
|---------|------|-------------|---------------|
| Use Case Diagrams (3) | `use_case_diagrams.puml` | PlantUML Online | PNG/SVG |
| Sequence Diagrams (4) | `sequence_diagrams.puml` | PlantUML Online | PNG/SVG |
| Class Diagram | `class_diagram.puml` | PlantUML Online | PNG/SVG |
| Architecture Diagram | `architecture_diagram.md` | Mermaid Live | PNG/SVG |
| DFD Diagrams (4) | `dfd_diagrams.md` | Mermaid Live | PNG/SVG |
| ER Diagram (2 versions) | `er_diagram.puml` | PlantUML Online | PNG/SVG |
| Activity Diagrams (4) | `activity_diagram.puml` | PlantUML Online | PNG/SVG |
| UI Wireframes | `ui_wireframes.md` | Figma/Draw.io | PNG |

---

## Step-by-Step Instructions

### For PlantUML Files (.puml)

1. **Online Method (Recommended)**:
   - Go to: https://www.plantuml.com/plantuml/uml/
   - Copy the code between `@startuml` and `@enduml`
   - Paste in the editor
   - Click "Submit"
   - Right-click image → Save as PNG

2. **VS Code Method**:
   - Install "PlantUML" extension by jebbs
   - Install Java JDK (required)
   - Open .puml file
   - Press `Alt + D` to preview
   - Right-click → Export PNG

### For Mermaid Files (.md)

1. **Online Method (Recommended)**:
   - Go to: https://mermaid.live/
   - Copy the code inside the ```mermaid block
   - Paste in the editor
   - Click "Download PNG" or "Download SVG"

2. **VS Code Method**:
   - Install "Mermaid Preview" extension
   - Open .md file
   - Click preview icon

---

## Diagram Checklist for Report

### Chapter 2: Requirement Engineering
- [ ] Fig. 2.1 - Use Case: Customer Self-Help (from `use_case_diagrams.puml`)
- [ ] Fig. 2.2 - Use Case: Voice Support (from `use_case_diagrams.puml`)
- [ ] Fig. 2.3 - Use Case: Admin Operations (from `use_case_diagrams.puml`)

### Chapter 3: Analysis & Design
- [ ] Fig. 3.1 - System Architecture (from `architecture_diagram.md`)
- [ ] Fig. 3.2 - Sequence: Self-Help Resolution (from `sequence_diagrams.puml`)
- [ ] Fig. 3.3 - Sequence: Ticket Creation (from `sequence_diagrams.puml`)
- [ ] Fig. 3.4 - Sequence: Voice Chat (from `sequence_diagrams.puml`)
- [ ] Fig. 3.5 - Class Diagram (from `class_diagram.puml`)
- [ ] Fig. 3.6 - DFD Level 0 (from `dfd_diagrams.md`)
- [ ] Fig. 3.7 - DFD Level 1 (from `dfd_diagrams.md`)
- [ ] Fig. 3.8 - ER Diagram (from `er_diagram.puml`)

### Chapter 5: Results (Screenshots/Wireframes)
- [ ] Fig. 5.1 - Landing Page (from `ui_wireframes.md` or actual screenshot)
- [ ] Fig. 5.2 - Self-Help Interface
- [ ] Fig. 5.3 - Ticket Submission Form
- [ ] Fig. 5.4 - Ticket with Screenshot
- [ ] Fig. 5.5 - Voice Chat Interface
- [ ] Fig. 5.6 - Ticket Status Tracking
- [ ] Fig. 5.7 - Admin Dashboard Overview
- [ ] Fig. 5.8 - Agent Ticket Analysis
- [ ] Fig. 5.9 - Response Sampling Interface
- [ ] Fig. 5.10 - Feedback Submission

### Optional (Activity Diagrams)
- [ ] Activity: Self-Help Flow (from `activity_diagram.puml`)
- [ ] Activity: Ticket Creation (from `activity_diagram.puml`)
- [ ] Activity: Voice Chat (from `activity_diagram.puml`)
- [ ] Activity: Agent Workflow (from `activity_diagram.puml`)

---

## Tips for Best Quality

1. **Export as SVG** for scalable quality in documents
2. **Use PNG at 2x resolution** if SVG not supported
3. **Consistent sizing**: Try to keep all diagrams similar width
4. **White background**: Ensure diagrams have white backgrounds for printing
5. **Readable font**: PlantUML default fonts work well, don't go below 10pt

---

## File Summary

```
diagrams/
├── README.md                    # Overview
├── RENDER_INSTRUCTIONS.md       # This file
├── use_case_diagrams.puml       # 3 Use Case diagrams
├── sequence_diagrams.puml       # 4 Sequence diagrams
├── class_diagram.puml           # 1 Class diagram
├── architecture_diagram.md      # System architecture (Mermaid)
├── dfd_diagrams.md              # DFD Level 0, 1 (Mermaid)
├── er_diagram.puml              # 2 ER diagram versions
├── activity_diagram.puml        # 4 Activity diagrams
└── ui_wireframes.md             # UI mockups (ASCII/specs)
```

**Total Diagrams: 18+**
