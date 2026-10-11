/**
 * The case a new hire practises on, shared by the apprentice's page and the stage.
 *
 * One definition, because the stage presents what the apprentice does: two copies of the
 * same invoice drift, and then the stage is showing a case nobody's page would book.
 *
 * Built to sit outside what the expert demonstrated: a supplier nobody has seen before,
 * and an amount between the threshold the law sets and the one the expert works to.
 */

export const PRACTICE_CASE = Object.freeze({
  invoice: 9931,
  supplier: "Novak Precision s.r.o.",
  supplier_known: false,
  amount_eur: 2400,
  category: "maintenance parts",
  asset_number: null,
});

/** What the action is about to do, in the words the review is given. */
export const PRACTICE_ACTION = "book this to maintenance";

/** The case as one sentence a person can listen to, field by field. */
export function caseAsSpeech(theCase, closing = "Press Enter to book it.") {
  const fields = Object.entries(theCase)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${value === null ? "none" : value}`)
    .join(". ");
  return `The case. ${fields}. ${closing}`.trim();
}
