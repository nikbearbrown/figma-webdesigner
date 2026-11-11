// Creates the `Palette` variable collection: seven color roles and two font-family slots,
// one mode per color set and light/dark. Run through the Figma MCP's use_figma tool.
//
// Do not paste hex values into this file. `./fad palettes --figma` (or `./fwd palettes --figma`)
// prints this script with the MODES line filled in from palettes/palettes.json; add an id to
// get one color set only (`./fad palettes northeastern --figma`).
//
// First run, 2026-11-10, education plan (student tier, Full seat): seven modes were accepted in one
// collection, and an eighth (the grey Wireframe mode, now the last entry of MODES) was added the same
// day. EB Garamond, Inter and Lato each had Regular, Medium and Bold.
// A plan that allows fewer modes shows up in `modeErrors`; nothing is hidden.
const MODES = __MODES__;

const existing = await figma.variables.getLocalVariableCollectionsAsync();
if (existing.find(c => c.name === 'Palette')) {
  throw new Error('A Palette collection already exists: ' + JSON.stringify(existing.map(c => ({ name: c.name, id: c.id, modes: c.modes.map(m => m.name) }))));
}

const fonts = await figma.listAvailableFontsAsync();
const have = (family, style) => fonts.some(f => f.fontName.family === family && f.fontName.style === style);
const fontReport = {};
for (const family of [...new Set(MODES.flatMap(m => [m.heading, m.body]))]) {
  fontReport[family] = ['Regular', 'Medium', 'Bold'].filter(s => have(family, s));
}

const hex = h => ({ r: parseInt(h.slice(1, 3), 16) / 255, g: parseInt(h.slice(3, 5), 16) / 255, b: parseInt(h.slice(5, 7), 16) / 255 });

const coll = figma.variables.createVariableCollection('Palette');
const modeIds = {};
const modeErrors = [];
coll.renameMode(coll.modes[0].modeId, MODES[0].name);
modeIds[MODES[0].name] = coll.modes[0].modeId;
for (const m of MODES.slice(1)) {
  try {
    modeIds[m.name] = coll.addMode(m.name);
  } catch (e) {
    modeErrors.push({ mode: m.name, error: String((e && e.message) || e) });
  }
}

// A role's scope is where Figma offers it in the picker. Never ALL_SCOPES.
const SCOPES = {
  'ground': ['FRAME_FILL', 'SHAPE_FILL'],
  'surface': ['FRAME_FILL', 'SHAPE_FILL'],
  'ink': ['TEXT_FILL', 'SHAPE_FILL', 'STROKE_COLOR'],
  'ink-soft': ['TEXT_FILL', 'SHAPE_FILL', 'STROKE_COLOR'],
  'border': ['STROKE_COLOR'],
  'accent': ['FRAME_FILL', 'SHAPE_FILL', 'TEXT_FILL', 'STROKE_COLOR'],
  'on-accent': ['TEXT_FILL', 'SHAPE_FILL', 'STROKE_COLOR'],
};
const camel = s => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
const variables = {};
for (const role of Object.keys(SCOPES)) {
  const v = figma.variables.createVariable('palette/' + role, coll, 'COLOR');
  v.scopes = SCOPES[role];
  v.setVariableCodeSyntax('WEB', 'var(--palette-' + role + ')');
  v.setVariableCodeSyntax('iOS', 'Palette.' + camel(role));
  v.setVariableCodeSyntax('ANDROID', 'palette' + camel(role).charAt(0).toUpperCase() + camel(role).slice(1));
  for (const m of MODES) {
    if (modeIds[m.name]) v.setValueForMode(modeIds[m.name], hex(m.roles[role]));
  }
  variables['palette/' + role] = v.id;
}

// Font families switch with the mode too, but only if every family is installed with the
// three weights the kit uses. Otherwise no type variables are made and text keeps a fixed font.
const typeErrors = [];
const allFontsOk = MODES.every(m => ['Regular', 'Medium', 'Bold'].every(s => have(m.heading, s) && have(m.body, s)));
if (allFontsOk) {
  for (const slot of ['heading', 'body']) {
    try {
      const v = figma.variables.createVariable('type/' + slot, coll, 'STRING');
      v.scopes = ['FONT_FAMILY'];
      for (const m of MODES) {
        if (modeIds[m.name]) v.setValueForMode(modeIds[m.name], m[slot]);
      }
      variables['type/' + slot] = v.id;
    } catch (e) {
      typeErrors.push({ slot, error: String((e && e.message) || e) });
    }
  }
}

// The write receipt. Ledger it as a figma.write event.
return {
  collectionId: coll.id,
  modesAsked: MODES.length,
  modesMade: coll.modes.map(m => ({ name: m.name, modeId: m.modeId })),
  modeErrors, typeErrors, allFontsOk, fontReport,
  variables,
  variableCount: coll.variableIds.length,
  createdNodeIds: [], mutatedNodeIds: [],
};
