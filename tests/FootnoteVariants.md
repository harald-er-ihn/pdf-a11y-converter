# A Demonstration of Footnote Variants

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.¹ Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.² Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.³ Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.⁴

## 1. Numeric footnotes – the standard form

Numeric footnotes are the most common. They appear as superscript numbers in the text and are listed at the bottom of the page.⁵ They can be used for citations,⁶ brief remarks,⁷ or even references to other sections.⁸ In academic writing, they often contain bibliographic details.⁹

Praesent sapien massa, convallis a pellentesque nec, egestas non nisi.¹⁰ Curabitur aliquet quam id dui posuere blandit. Nulla quis lorem ut libero malesuada feugiat.¹¹ Vestibulum ac diam sit amet quam vehicula elementum sed sit amet dui.¹²

## 2. Symbolic footnotes – for special cases

For notes that should stand out or when numeric sequences are already occupied, symbols are used. Traditional order is: * (asterisk), † (dagger), ‡ (double dagger), § (section mark).¹³

*   Asterisk footnotes often indicate author’s notes or disclaimers.¹⁴
†   Dagger footnotes are frequently used for obituaries or corrections.¹⁵
‡   Double dagger marks third‑level remarks.¹⁶
§   Section marks may refer to legal or structural notes.¹⁷

## 3. Reusable footnotes – same note, multiple references

Sometimes a single footnote is referenced several times. In Markdown you can achieve this by reusing the same identifier.¹⁸

-   First occurrence of this note.¹⁸
-   Second occurrence of the same note later in the text.¹⁸
-   Even a third time – all point to the identical explanatory text.¹⁸

This is especially useful when a term or concept needs repeated clarification without duplicating the note content.

## 4. Footnotes with multiple paragraphs

Footnotes are not limited to a single paragraph. They can contain two or more paragraphs to hold longer explanations or quotations.

Here is a footnote with two paragraphs:¹⁹

*   The first paragraph of this footnote provides additional context. It can be several lines long.
    The second paragraph is indented (or separated by a blank line) and continues the discussion. This allows for structured notes that include arguments, examples, or even citations within citations.

## 5. Complex content inside footnotes

Footnotes can host almost any Markdown element: lists, code blocks, blockquotes, and inline formatting.

A footnote containing a numbered list:²⁰

1.  First item of the list inside the footnote.
2.  Second item with **bold** and *italic* text.
3.  Third item showing `inline code`.

Another footnote demonstrates a code block:²¹

```python
def hello():
    print("This code lives inside a footnote!")
    
```
## 6. Footnotes with hyperlinks

Modern digital documents often embed URLs directly in footnotes.²³

Here the footnote itself contains a clickable link:²⁴ [Example Domain](https://example.com).

## 7. Combined and nested variants

To show everything together, consider this sentence that references a footnote with symbols, multiple paragraphs, and a list.²⁵

Additionally, we can combine symbolic and numeric footnotes in the same document. For instance, the dagger note from earlier¹⁵ can be paired with a numeric reference.⁶
    
    
## 8. End of the main text

The following footnotes illustrate that even tables can be included, though their rendering depends on the output engine.²⁶

Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur?²⁷ Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?²⁸

---

## Footnotes

[^1]: A simple numeric footnote – the most basic variant.

[^2]: Numeric footnote with **bold** and *italic* formatting. Also supports `inline code`.

[^3]: Another numeric footnote, this one containing a [link](https://www.example.com).

[^4]: Numeric footnote with a citation: *Smith, J. (2020). The Art of Footnotes. Oxford University Press.*

[^5]: Numeric footnote referencing the standard footnote style.

[^6]: Numeric footnote used for a citation to a secondary source.

[^7]: Numeric footnote with just a brief remark.

[^8]: Numeric footnote pointing to §1.2.

[^9]: Numeric footnote with full bibliographic data: *Doe, J. (2019). “A Study of Footnotes.” Journal of Typography, 15(3), 45–67.*

[^10]: Numeric footnote used to clarify a technical term.

[^11]: Numeric footnote that continues the explanation from the previous note.

[^12]: Final numeric footnote in this sequence.

[^13]: *Asterisk footnote* – usually the first symbolic note.  
    † *Dagger footnote* – often used for a second level.  
    ‡ *Double dagger* – third level.  
    § *Section mark* – fourth level.  
    **Note:** Symbolic order may vary by style guide.

[^14]: Asterisk footnote explaining that this note is purely illustrative.

[^15]: Dagger footnote – in this document it signals an example of a reusable concept.

[^16]: Double dagger footnote – contains a short list of common footnote symbols: *, †, ‡, §.

[^17]: Section mark footnote – references §2 of this document.

[^18]: **Reusable footnote** – all occurrences of `[^18]` point here. This text appears only once in the footnotes section but is referenced multiple times in the main body.    

[^19]: This is the first paragraph of the multi‑paragraph footnote.  
    It can contain additional details.  

    And here is the second paragraph. Notice the blank line between paragraphs. This footnote also demonstrates that footnotes can be quite long without affecting the flow of the main text.

[^20]: **Numbered list inside a footnote**  
    1.  Item one.  
    2.  Item two.  
    3.  Item three.

[^21]: **Code block inside a footnote**  
    ```python
    # Example code
    for i in range(3):
        print(f"Footnote iteration {i}")
    ```
[^22]: > **Blockquote inside a footnote**  
    > This blockquote is part of a footnote. It can contain citations or extended excerpts.
[^23]: Hyperlink footnote: [Wikipedia on Footnotes](https://en.wikipedia.org/wiki/Note_(typography))
[^24]: Another hyperlink footnote: [Pandoc documentation](https://pandoc.org/)
[^25]: **Combination footnote** – this note uses:
    *   A symbol (double dagger) as its marker, because we reused `[^16]`? Actually this is a new footnote `[^25]` that contains a list, bold text, and a link: [Learn more about footnotes](https://en.wikipedia.org/wiki/Note_(typography)).
[^26]: **Table inside a footnote**  
    | Variant      | Example        |
    |--------------|----------------|
    | Numeric      | ¹, ², ³        |
    | Symbolic     | *, †, ‡, §     |
    | Reusable     | [^18]          |
[^27]: Numeric footnote referencing the final thoughts.
[^28]: Final footnote of the document. It shows that footnotes can be placed anywhere and their order is determined by the processing engine (typically sequential).    
