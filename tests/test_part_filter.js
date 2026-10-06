const assert = require('node:assert/strict');
const fs = require('node:fs');
const { filterPartNumbers } = require('../ui_helpers.js');

const parts = ['PN-100A', 'Widget-250', 'PN-200B'];

assert.deepEqual(filterPartNumbers(parts, 'pn-'), ['PN-100A', 'PN-200B']);
assert.deepEqual(filterPartNumbers(parts, '  widget '), ['Widget-250']);
assert.deepEqual(filterPartNumbers(parts, ''), parts);
assert.deepEqual(filterPartNumbers(null, 'pn'), []);
assert.deepEqual(filterPartNumbers(['PN-1', null, 22], ''), ['PN-1']);

const page = fs.readFileSync('Production_Select.html', 'utf8');
const pickerStart = page.indexOf('<div id="partPicker"');
const dropdownStart = page.indexOf('<div id="partDropdown"', pickerStart);
const searchInput = page.indexOf('<input id="partSearch"', dropdownStart);
const searchStatus = page.indexOf('<div id="partSearchStatus"', searchInput);
const statusClose = page.indexOf('</div>', searchStatus);
const dropdownClose = page.indexOf('</div>', statusClose + '</div>'.length);
assert.match(page.slice(pickerStart, page.indexOf('>', pickerStart) + 1), /\shidden>/);
assert.ok(pickerStart >= 0 && dropdownStart > pickerStart);
assert.ok(searchInput > dropdownStart && searchStatus > searchInput && dropdownClose > searchStatus);

console.log('Part-number filter and integrated dropdown tests passed.');
