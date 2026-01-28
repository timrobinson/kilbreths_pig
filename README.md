<table>
  <tr>
    <td width="40%">
      <img src="logo.png" alt="Kilbreth's Pig logo" width="100%">
    </td>
    <td width="70%">
      <h1>Kilbreth's Pig</h1>
      <p>
        Kilbreth’s Pig is a Python-based system designed to validate academic citations by extracting
references from a PDF, identifying key metadata, querying authoritative databases, and
generating a structured validation report. The system addresses a growing problem: AI-
generated citations often contain fabricated or partially incorrect information. Kilbreth’s Pig
acts as a filter—much like the pig in the family story that inspired the name—sorting valuable
information from slop.
      </p>
    </td>
  </tr>
</table>

This document outlines the full architecture goals of the system, including three deployment options:

- A fast, interactive web interface using GitHub Pages and an external backend

- A fully in-browser version using WebAssembly-based Python

- A GitHub Actions–driven workflow for reproducible, version-controlled validation

All options rely on a shared core Python library that performs deterministic, API-driven
validation.
