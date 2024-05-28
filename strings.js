const { readFileSync } = require('fs');

exports.getString = function(file, section, key) {
    const content = readFileSync(file, 'utf8');
    const regex = new RegExp(`^\\[${section}\\][^]*?${key}[^=]*=\\s*"(.*)"`, 'm');
    const match = content.match(regex);
    return match ? match[1] : '';
};

