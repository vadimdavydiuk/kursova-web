const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(__dirname + '/static/js/main.js', 'utf8');
const prices = [189, 239, 259, 229, 269, 249, 219, 259];
const factors = {small: 85, medium: 100, large: 130};
let checks = 0;
for (const base of prices) {
  for (const [size, factor] of Object.entries(factors)) {
    for (let qty = 1; qty <= 10; qty++) {
      const priceNode = {textContent: ''};
      const listeners = {};
      const form = {
        dataset: {price: String(base)},
        querySelector: selector => selector === '[data-live-price]' ? priceNode :
          {value: selector === '[name=size]' ? size : String(qty)},
        addEventListener: (name, handler) => {listeners[name] = handler;}
      };
      vm.runInNewContext(source, {document: {
        querySelectorAll: selector => selector === '.order-form' ? [form] : []
      }});
      const expected = Math.floor((base * factor + 50) / 100) * qty;
      assert.equal(priceNode.textContent, `${expected} грн`);
      listeners.change();
      assert.equal(priceNode.textContent, `${expected} грн`);
      listeners.input();
      assert.equal(priceNode.textContent, `${expected} грн`);
      checks++;
    }
  }
}
assert.equal(Math.round(239 * 1.3) * 2, 622);
console.log(`PASS: ${checks}/240 combinations; initial render, change and input; Pepperoni large x2 = 622 UAH.`);
