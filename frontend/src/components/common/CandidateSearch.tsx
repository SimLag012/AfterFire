export function CandidateSearch({value, onChange}: {value: string; onChange: (value: string) => void}) {
  return <label className="block py-2 text-sm">Search candidates
    <input type="search" className="candidate-filter mt-1 block w-full p-2 text-slate-100"
      placeholder="ID, place, name or date" value={value} onChange={event => onChange(event.target.value)} />
  </label>;
}
