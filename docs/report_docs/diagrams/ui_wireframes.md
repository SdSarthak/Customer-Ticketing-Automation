# UI Wireframes / Mockups

## These can be recreated in Figma, Draw.io, or Balsamiq

---

## Fig. 5.1 - Customer Portal Landing Page

```
┌─────────────────────────────────────────────────────────────────┐
│  🎧 AI Customer Support                    [EN ▼] [🔊 Voice]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                    Welcome to Support                           │
│            Get instant help powered by AI                       │
│                                                                 │
│    ┌─────────────────────┐    ┌─────────────────────┐         │
│    │                     │    │                     │         │
│    │   💬 Get Help Now   │    │   📝 Submit Ticket  │         │
│    │                     │    │                     │         │
│    │   Try self-help     │    │   Create formal     │         │
│    │   resolution first  │    │   support request   │         │
│    │                     │    │                     │         │
│    └─────────────────────┘    └─────────────────────┘         │
│                                                                 │
│    ┌─────────────────────────────────────────────────┐         │
│    │  🔍 Track Your Ticket                           │         │
│    │  ┌──────────────────────────────┐ [Track]       │         │
│    │  │ Enter Ticket ID...           │               │         │
│    │  └──────────────────────────────┘               │         │
│    └─────────────────────────────────────────────────┘         │
│                                                                 │
│    ──────────────────────────────────────────────────          │
│                                                                 │
│    📊 Current Wait Times:  Urgent: ~30min | High: ~2hrs       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fig. 5.2 - Self-Help Interface

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back                    Self-Help                    [🎤]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Describe your issue:                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                                                           │ │
│  │  I can't login to my account. It says my password is     │ │
│  │  incorrect but I'm sure I'm using the right one.         │ │
│  │                                                           │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  🌐 Detected Language: English              [Get Help →]       │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅ Here are steps to resolve your issue:                      │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ 1. Clear your browser cache and cookies, then try        │ │
│  │    logging in again using the correct email address.     │ │
│  │                                                           │ │
│  │ 2. Click "Forgot Password" on the login page to reset    │ │
│  │    your password. Check your email for the reset link.   │ │
│  │                                                           │ │
│  │ 3. If the issue persists, ensure Caps Lock is off and    │ │
│  │    try logging in from a different browser or device.    │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐           │
│  │ ✓ Issue Resolved     │  │ Still Need Help? →   │           │
│  └──────────────────────┘  └──────────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fig. 5.3 - Ticket Submission Form

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back                  Submit Ticket                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Your Name *                                                    │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ John Doe                                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Email Address *                                                │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ john.doe@example.com                                      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Describe Your Issue *                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ I was charged twice for my subscription this month.      │ │
│  │ The first charge was on the 1st and then again on the   │ │
│  │ 5th. I need a refund for the duplicate charge.          │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Screenshot (Optional)                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                                                           │ │
│  │     📎 Drag and drop image here or click to browse       │ │
│  │                                                           │ │
│  │     Supported: PNG, JPG, GIF, WebP (max 10MB)            │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│                              ┌────────────────────────────────┐│
│                              │       Submit Ticket →          ││
│                              └────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fig. 5.7 - Admin Dashboard Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🎧 Support Dashboard                          Agent: Jane Smith  [Logout] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─ Filters ────────────────────────────────────────────────────────────┐  │
│  │ Status: [All ▼]  Priority: [All ▼]  Category: [All ▼]  [🔄 Refresh] │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ Ticket Queue ───────────────────────────────────────────────────────┐  │
│  │ ID              │ Customer      │ Category      │ Priority │ Status  │  │
│  ├─────────────────┼───────────────┼───────────────┼──────────┼─────────┤  │
│  │ TKT-20250415-01 │ john@mail.com │ Billing       │ 🔴 Urgent│ Open    │  │
│  │ TKT-20250415-02 │ sara@mail.com │ Tech Support  │ 🟠 High  │ Open    │  │
│  │ TKT-20250414-15 │ mike@mail.com │ Account Mgmt  │ 🟡 Medium│ Progress│  │
│  │ TKT-20250414-12 │ lisa@mail.com │ Returns       │ 🟢 Low   │ Resolved│  │
│  │ TKT-20250414-08 │ tom@mail.com  │ Shipping      │ 🟡 Medium│ Open    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ Quick Stats ────────────────────────────────────────────────────────┐  │
│  │  📊 Open: 12  │  ⏳ In Progress: 5  │  ✅ Resolved Today: 8         │  │
│  │  🔴 Urgent: 2 │  🟠 High: 4         │  📧 Avg Response: 1.5 hrs     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ System Health ──────────────────────────────────────────────────────┐  │
│  │  ✅ RAG Engine: Ready (1,250 docs)  │  ✅ MongoDB: Connected        │  │
│  │  ✅ Groq API: Available             │  ✅ Email Service: Active     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Fig. 5.9 - Response Sampling Interface

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Ticket: TKT-20250415-0001                              [← Back to Queue]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Customer: john@example.com          Category: Billing                     │
│  Issue: Charged twice for subscription                                     │
│  Sentiment: 😠 Negative              Priority: 🔴 Urgent (SLA: 2 hrs)      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                        Response Samples                                     │
│  ┌─────────────────────┬─────────────────────┬─────────────────────┐       │
│  │ 🧊 Conservative     │ ⚖️ Balanced          │ 🎨 Creative         │       │
│  │ (temp: 0.3)         │ (temp: 0.7)         │ (temp: 1.0)         │       │
│  ├─────────────────────┼─────────────────────┼─────────────────────┤       │
│  │ Dear Customer,      │ Hi John,            │ Hello John! 👋      │       │
│  │                     │                     │                     │       │
│  │ We apologize for    │ I'm sorry to hear   │ I completely        │       │
│  │ the duplicate       │ about the duplicate │ understand how      │       │
│  │ charge. Our billing │ charge on your      │ frustrating this    │       │
│  │ team will process   │ account. I've       │ must be! We've      │       │
│  │ a refund within     │ already initiated   │ already flagged     │       │
│  │ 3-5 business days.  │ a refund for you,   │ this for immediate  │       │
│  │                     │ and you should see  │ refund, and I'm     │       │
│  │ Best regards,       │ it within 48 hours. │ personally tracking │       │
│  │ Support Team        │                     │ it to ensure...     │       │
│  │                     │ Let me know if you  │                     │       │
│  │                     │ have any questions! │                     │       │
│  ├─────────────────────┼─────────────────────┼─────────────────────┤       │
│  │     [📋 Copy]       │     [📋 Copy]       │     [📋 Copy]       │       │
│  │     [✓ Select]      │     [✓ Select]      │     [✓ Select]      │       │
│  └─────────────────────┴─────────────────────┴─────────────────────┘       │
│                                                                             │
│  ┌─ Edit Selected Response ─────────────────────────────────────────────┐  │
│  │ Hi John, I'm sorry about the duplicate charge. I've initiated...    │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  Status: [In Progress ▼]        [💾 Save Draft]  [📤 Send Response]       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Fig. 5.5 - Voice Chat Interface

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back                  Voice Support                    🔊   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                                                                 │
│                         ┌───────────┐                          │
│                         │           │                          │
│                         │    🎤     │                          │
│                         │           │                          │
│                         │  ● REC    │                          │
│                         └───────────┘                          │
│                      Press to Record                           │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│                                                                 │
│  📝 Transcription:                                              │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ "I need help with my recent order. It hasn't arrived     │ │
│  │  yet and it's been over a week."                         │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  🌐 Detected: English                                          │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│                                                                 │
│  🔊 AI Response:                                                │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ ▶️ Playing audio response...                              │ │
│  │ ━━━━━━━━━━━━━━━━━●━━━━━━━━━  0:45 / 1:23                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Text: "I understand your concern about the delayed order.     │
│  Here are steps to track your shipment: First, check your     │
│  email for tracking information..."                            │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ 🎤 Ask Follow-up │  │ 📝 Create Ticket │                   │
│  └──────────────────┘  └──────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
