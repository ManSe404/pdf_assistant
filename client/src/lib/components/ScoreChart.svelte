<!--
	Satisfaction per component as horizontal bars (one series, so no legend), with a
	table of the exact numbers. Inactive components are dimmed in both.
-->
<script lang="ts" module>
	import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from 'chart.js';

	// Only the parts a bar chart needs, so the rest of chart.js is tree-shaken.
	Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);
</script>

<script lang="ts">
	import type { ChartConfiguration } from 'chart.js';
	import type { Attachment } from 'svelte/attachments';
	import type { ComponentScore } from '../api/types.ts';
	import { formatPercent } from '../format.ts';

	interface Props {
		title: string;
		scores: ComponentScore[];
	}

	let { title, scores }: Props = $props();

	// Tailwind blue-600 for active components, gray-300 for inactive ones.
	const ACTIVE = '#2563eb';
	const INACTIVE = '#d1d5db';
	const GRID = '#e5e7eb';
	const TEXT = '#374151';
	const MUTED = '#9ca3af';

	const tableId = $props.id();

	function config(rows: ComponentScore[]): ChartConfiguration<'bar', (number | null)[], string> {
		const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		return {
			type: 'bar',
			data: {
				labels: rows.map((s) => s.label),
				datasets: [
					{
						data: rows.map((s) => (s.satisfaction === null ? null : s.satisfaction * 100)),
						backgroundColor: rows.map((s) => (s.active ? ACTIVE : INACTIVE)),
						borderRadius: 4,
						borderSkipped: 'start',
						maxBarThickness: 24
					}
				]
			},
			options: {
				indexAxis: 'y',
				responsive: true,
				maintainAspectRatio: false,
				animation: reduceMotion ? false : { duration: 300 },
				scales: {
					x: {
						min: 0,
						max: 100,
						border: { display: false },
						grid: { color: GRID },
						ticks: {
							stepSize: 25,
							color: TEXT,
							callback: (value) => formatPercent(Number(value) / 100)
						}
					},
					y: {
						grid: { display: false },
						border: { color: GRID },
						ticks: {
							color: (context) => (rows[context.index]?.active === false ? MUTED : TEXT)
						}
					}
				},
				plugins: {
					legend: { display: false },
					tooltip: {
						callbacks: {
							label: (context) => {
								const s = rows[context.dataIndex];
								const satisfaction =
									s.satisfaction === null ? 'bez glasova' : formatPercent(s.satisfaction);
								return [
									`Zadovoljstvo: ${satisfaction}`,
									`Glasovi: ${s.up} za, ${s.down} protiv`,
									`Težina izbora: ${formatPercent(s.weight)}`,
									...(s.active ? [] : ['Neaktivna'])
								];
							}
						}
					}
				}
			}
		};
	}

	// Re-created whenever `scores` changes.
	const chart: Attachment<HTMLCanvasElement> = (canvas) => {
		const instance = new Chart(canvas, config(scores));
		return () => instance.destroy();
	};
</script>

<section class="rounded-xl border border-gray-200 bg-white p-4" aria-labelledby="{tableId}-title">
	<h2 id="{tableId}-title" class="font-semibold">{title}</h2>

	{#if scores.length === 0}
		<p class="mt-2 text-sm text-gray-500">Nema komponenti.</p>
	{:else}
		<div class="relative mt-3" style:height="{scores.length * 40 + 40}px">
			<!-- The table below carries the same numbers for screen readers. -->
			<canvas {@attach chart} aria-hidden="true"></canvas>
		</div>

		<div class="mt-3 overflow-x-auto">
			<table id={tableId} class="w-full text-left text-sm">
				<caption class="sr-only">{title}: glasovi, zadovoljstvo i težina izbora</caption>
				<thead class="text-xs text-gray-500">
					<tr class="border-b border-gray-200">
						<th scope="col" class="py-1.5 pr-3 font-medium">Komponenta</th>
						<th scope="col" class="px-2 py-1.5 text-right font-medium">Za</th>
						<th scope="col" class="px-2 py-1.5 text-right font-medium">Protiv</th>
						<th scope="col" class="px-2 py-1.5 text-right font-medium">Zadovoljstvo</th>
						<th scope="col" class="py-1.5 pl-2 text-right font-medium">Težina izbora</th>
					</tr>
				</thead>
				<tbody>
					{#each scores as score (score.name)}
						<tr
							class={['border-b border-gray-100 last:border-0', !score.active && 'text-gray-400']}
						>
							<th scope="row" class="py-1.5 pr-3 font-normal">
								{score.label}
								{#if !score.active}
									<span class="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs">neaktivna</span>
								{/if}
							</th>
							<td class="px-2 py-1.5 text-right tabular-nums">{score.up}</td>
							<td class="px-2 py-1.5 text-right tabular-nums">{score.down}</td>
							<td class="px-2 py-1.5 text-right tabular-nums">
								{score.satisfaction === null ? '–' : formatPercent(score.satisfaction)}
							</td>
							<td class="py-1.5 pl-2 text-right tabular-nums">{formatPercent(score.weight)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>
