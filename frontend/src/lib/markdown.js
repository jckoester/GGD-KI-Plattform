import { marked } from 'marked';
import DOMPurify from 'dompurify';

const renderer = new marked.Renderer();

renderer.link = ({ href, title, text }) => {
    const titleAttr = title ? ` title="${title}"` : '';
    return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

marked.use({ gfm: true, breaks: true, renderer });

export function renderMarkdown(text) {
    if (!text) return '';
    return DOMPurify.sanitize(marked.parse(text), { ADD_ATTR: ['target', 'rel'] });
}
