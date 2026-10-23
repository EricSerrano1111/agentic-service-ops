// The elapsed timer's wording (data dictionary section 6, rule 7). Both functions take only a
// number of milliseconds measured in the browser; nothing from a response is ever passed in.

/** "Working… N s": whole seconds, rounded down. */
export function workingLabel(ms) {
  return `Working… ${Math.floor(Math.max(0, ms) / 1000)} s`;
}

/** "Answered in N.N s" after a response, "Ended after N.N s" after an error or a refusal. */
export function finishedLabel(ms, answered) {
  const seconds = (Math.max(0, ms) / 1000).toFixed(1);
  return answered ? `Answered in ${seconds} s` : `Ended after ${seconds} s`;
}
