// Serbian (Latin) formatting of dates, sizes and shares.

const LOCALE = 'sr-Latn-RS';

const dateTime = new Intl.DateTimeFormat(LOCALE, {
	day: 'numeric',
	month: 'numeric',
	year: 'numeric',
	hour: '2-digit',
	minute: '2-digit'
});
const decimal = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat(LOCALE, { style: 'percent', maximumFractionDigits: 0 });

export function formatDateTime(iso: string): string {
	const date = new Date(iso);
	return Number.isNaN(date.getTime()) ? iso : dateTime.format(date);
}

export function formatSize(bytes: number): string {
	if (bytes < 1024) {
		return `${bytes} B`;
	}
	if (bytes < 1024 * 1024) {
		return `${Math.round(bytes / 1024)} KB`;
	}
	return `${decimal.format(bytes / (1024 * 1024))} MB`;
}

export function formatPercent(fraction: number): string {
	return percent.format(fraction);
}
