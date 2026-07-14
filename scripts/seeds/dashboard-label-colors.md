### Bug description

When using `label_colors` in dashboard JSON metadata, some charts intermittently do not apply the defined colors in "label_colors" and instead fall back to the chart's default `color_scheme` on initial render.

This issue does not affect all charts consistently:
- Most of the charts correctly apply `label_colors`
- Some charts (often the first one) fall back to the default color scheme
- The behavior is highly intermittent and not reproducible on every page load

---

### Observed behavior

- Only some charts are affected, while others display correct colors
- After user interaction (e.g. clicking legend or refreshing the page), the colors become correct

---

### Expected behavior

All charts should consistently apply the `label_colors` defined in dashboard metadata on initial render.

---

### Dashboard label_colors configuration

The dashboard uses the following `label_colors` configuration:

```json
{
  "label_colors": {
    "60_Crashed": "#8b0000",
    "50_Error": "#ff0000",
    "40_Failed": "#ff8c00",
    "30_Undefined": "#ffd700",
    "20_Passed": "#008000",
    "10_Executed": "#0000ff",
    "01_Invalid": "#ff00ff",
    "00_NoResult": "#808080"
  }
}
```
Dashboard-level color_scheme is empty, the charts use "supersetColors" as color_scheme.

---

### Screenshots/recordings

The following screenshot shows the case when the issue occurs

<img width="1770" height="556" alt="Image" src="https://github.com/user-attachments/assets/531f7100-cf1f-4eb8-818e-cdb2116d930c" />

After refreshing or clicking legend, the colors become correct

<img width="1906" height="653" alt="Image" src="https://github.com/user-attachments/assets/b23b3ae5-b18d-41eb-94cb-617db6851329" />


---
### Superset version

6.0.0

---

### Python version

I don't know

### Node version

I don't know

### Browser

Chrome


### Additional context

I have reviewed similar issues related to color assignment and dashboard behavior (e.g. #36406), but I could not find a case fully matching this behavior (intermittent fallback to `color_scheme` with `label_colors` defined).

Based on the observed behavior, it seems likely that this is related to rendering order or timing in the frontend. However, this is only a hypothesis.

I would appreciate confirmation from maintainers whether this is an expected limitation, a known issue, or a bug in the current rendering pipeline. Thanks.
``

### Checklist

- [x] I have searched Superset docs and Slack and didn't find a solution to my problem.
- [x] I have searched the GitHub issue tracker and didn't find a similar bug report.
- [x] I have checked Superset's logs for errors and if I found a relevant Python stacktrace, I included it here as text in the "additional context" section.