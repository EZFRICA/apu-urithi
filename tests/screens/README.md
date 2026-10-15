# Screens to share

Pages made to be shared on screen during a real-condition test of the classroom mode
(`guardian/ui/teach/classroom.js`): a guardian works on one of them while Urithi watches, asks
why at the pauses, and notes what it saw and proposes it; the guardian saves what counts
(decision 0016). Nothing here is served by Urithi, read by pytest, or sent anywhere; each page
keeps its own state in the browser only.

| Page | Knowledge it goes with | The decisions in it |
| --- | --- | --- |
| `invoice-desk.html` | Code a supplier invoice | equipment over 5 000 euros as capex, an IBAN that differs from the vendor master, an invoice with no purchase order |
| `community-desk.html` | Building and leading a tech community | announcing a meetup publicly two weeks ahead, choosing two talks of four, assigning a code of conduct report to two organisers not involved, answering a newcomer |

## Using one

1. Open the page in Chrome straight from the file (`file://`), or from its published copy.
2. In another tab, open `http://localhost:8790/teach/` as the guardian, start the knowledge,
   open the classroom and choose the screen; share the page's tab.
3. Take one decision at a time and pause a few seconds after each, so the question comes.
4. "Start the practice again" puts every decision back.

Each action changes something visible (a status, a coloured message, a line in the log), in
type large enough to read at two frames a second. The data is invented: the companies, people
and numbers are fictional.

## Adding one

One self-contained HTML file, no call to any server, light and dark themes, a reset button,
and a log of what was done. Say here which knowledge it goes with and what it decides.
