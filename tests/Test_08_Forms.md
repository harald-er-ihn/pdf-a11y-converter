---
header-includes:
  - \usepackage{hyperref}
---

# Antrag auf Kostenübernahme (Barrierefreiheit)

Bitte füllen Sie das folgende Formular vollständig aus. Der `form_worker` extrahiert diese interaktiven AcroForm-Felder und stellt sicher, dass sie im PDF/UA-Dokument zugänglich bleiben.

\begin{Form}
\textbf{Antragsteller (Name, Vorname):} \\
\TextField[name=fullname, width=10cm, bordercolor=0 0 0]{}

\vspace{0.5cm}

\textbf{Abteilung:} \\
\TextField[name=department, width=10cm, bordercolor=0 0 0]{}

\vspace{0.5cm}

\textbf{Ich bestätige die Richtigkeit der Angaben:} \\
\CheckBox[name=confirm, bordercolor=0 0 0]{ Ja, ich stimme zu.}
\end{Form}

Bitte drucken Sie das Dokument nach dem Ausfüllen nicht aus, sondern reichen Sie es digital ein, um die semantischen Tags nicht zu zerstören.
