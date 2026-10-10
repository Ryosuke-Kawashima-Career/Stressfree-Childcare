# Care & Learn frontend preview

From `D:\hackathons\humanity` run:

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory frontend
```

Open http://127.0.0.1:4173. No install or build is required. Use HTTP rather than opening index.html directly so JSON fixtures load.

Six fictional Gurgaon centers provide the interactive design preview. Search, category, cost, vaccination filter, list/pin selection, details, reset, and contextual inquiry previews work. The map is a labeled local illustration. Addresses, fees, schedules, and services are demo examples. No external tiles or contact links are included before direction review.

Review desktop and phone widths, keyboard navigation, and these flows:
1. Vaccination banner → health center → inquiry preview.
2. Clear filters → Learning + Free → learning center → inquiry preview.
3. Unmatched search → empty results → reset.
4. Select a center → exclude it with filters → details clear and map/list agree.
