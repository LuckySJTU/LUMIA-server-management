import { describe, test, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import JobResources from '@/components/jobs/JobResources.vue'
import jobs from '../../assets/jobs.json'

describe('JobResources.vue', () => {
  test('job with gpus', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 4
    job.cpus.number = 16
    job.gres_detail = ['gpu:h100:2(IDX:2-3)']
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items.length).toBe(4)
    expect(items[0].text()).toBe('4')
    expect(items[1].text()).toBe('16')
    expect(items[2].text()).toBe('-')
    expect(items[3].text()).toBe('2')
  })
  test('job without gpus', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 2
    job.cpus.number = 8
    job.gres_detail = []
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items.length).toBe(3)
    expect(items[0].text()).toBe('2')
    expect(items[1].text()).toBe('8')
    expect(items[2].text()).toBe('-')
  })
  test('job with gpus unreliable', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 4
    job.cpus.number = 16
    job.gres_detail = []
    job.tres_per_socket = 'gres/gpu:2'
    job.sockets_per_node.set = true
    job.sockets_per_node.number = 2
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items.length).toBe(5)
    expect(items[0].text()).toBe('4')
    expect(items[1].text()).toBe('16')
    expect(items[2].text()).toBe('-')
    expect(items[3].text()).toBe('16 ~')
    expect(items[4].text()).toBe('~')
  })
  test('job with memory in GB rounded up', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 1
    job.cpus.number = 4
    job.gres_detail = []
    job.tres_per_node = 'mem:2500M'
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items[2].text()).toBe('3')
  })

  test('job with memory from tres_req_str', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 1
    job.cpus.number = 4
    job.gres_detail = []
    job.tres_req_str = 'cpu=4,mem=1537M,node=1,billing=4'
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items[2].text()).toBe('2')
  })

  test('job prefers allocated resources from tres_alloc_str', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 8
    job.cpus.number = 32
    job.gres_detail = []
    job.tres_req_str = 'cpu=32,mem=16G,node=8,billing=32'
    job.tres_alloc_str = 'cpu=10,mem=2500,node=2,billing=10'
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items[0].text()).toBe('2')
    expect(items[1].text()).toBe('10')
    expect(items[2].text()).toBe('3')
  })

  test('job parses allocated memory unit from tres_alloc_str', () => {
    const job = { ...jobs[0] }
    job.node_count.number = 1
    job.cpus.number = 4
    job.gres_detail = []
    job.tres_alloc_str = 'cpu=4,mem=100G,node=1,billing=4'
    const wrapper = mount(JobResources, {
      props: {
        job: job
      }
    })
    const items = wrapper.findAll('span')
    expect(items[2].text()).toBe('100')
  })
})
