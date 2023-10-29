import { translate } from '@vitalets/google-translate-api';

async function performTranslation() {
    if (process.argv.length < 4) {
        console.error('Usage: node translate.js <text_to_translate> <target_language> [<source_language>]');
        process.exit(1);
    }

    const textToTranslate = process.argv[2];
    const targetLanguage = process.argv[3];
    var sourceLanguage = process.argv[4];
    if (sourceLanguage === undefined) {
        sourceLanguage = 'auto';
    }

    try {
        const { text } = await translate(textToTranslate, { to: targetLanguage, from: sourceLanguage });
        console.log(text);
    } catch (error) {
        console.error('Error:', error.message);
    }
}

performTranslation();